#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_exam.py  –  Random 2nd Exercise Exam Generator
VU Mechanik – LAWI 100515 (PI) · BOKU Wien

Generates exam sheet + full solution (German & English) as LaTeX + PDF.

SYSTEM (BSP 1)
  Cantilever beam A–C–G (clamped at A) + planar truss C–D–E–F–B (roller at B).
  Members [1],[2]: beam; [3]–[9]: truss.
  Loads: uniform load q on beam, horizontal point load P at truss node D.

USAGE
  python exam_generator/generate_exam.py                     # random seed
  python exam_generator/generate_exam.py --seed 42 --group B
  python exam_generator/generate_exam.py --date 2026-07-15 --semester "SS 2026"
  python exam_generator/generate_exam.py --no-compile        # .tex files only
"""
from __future__ import annotations

import argparse
import math
import os
import random
import subprocess
import sys
from datetime import date as _today
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# 1.  SOLUTION  (compute every quantity from random parameters)
# ══════════════════════════════════════════════════════════════════════════════

def build_solution(seed: int) -> dict:
    rng = random.Random(seed)

    # ── BSP 1 system values ──────────────────────────────────────────────────
    L  = rng.choice([0.5, 1.0, 1.5, 2.0])          # span [m]
    q  = float(rng.choice([2, 3, 4, 5, 6]))         # distributed load [kN/m]
    P  = float(rng.choice([8, 10, 12, 15, 16, 20])) # point load [kN]

    # ── BSP 1 reactions ──────────────────────────────────────────────────────
    # Truss subsystem: ΣM_C=0, ΣFx=0, ΣFy=0
    BV = -P / 2
    AH = -P
    AV = 2 * q * L + P / 2
    MA = 2 * q * L ** 2 + P * L / 2

    # ── BSP 1 section forces ─────────────────────────────────────────────────
    # Stab [1]: A→C, running variable x ∈ [0, L]
    def N1(x): return P
    def V1(x): return (2 * q * L + P / 2) - q * x
    def M1(x): return (2 * q * L + P / 2) * x - (q / 2) * x ** 2 - MA

    # Stab [2]: C→G, running variable x ∈ [0, L]
    def N2(x): return 0.0
    def V2(x): return q * (L - x)
    def M2(x): return -(q / 2) * (L - x) ** 2

    # ── BSP 1 truss member forces ─────────────────────────────────────────────
    # Rundschnitt at B: members [8] (B→E, dir -1,+1/√2) and [9] (B→F, dir -1,0)
    S8 = P / math.sqrt(2)          # Zug  (tension)
    S9 = -P / 2                     # Druck (compression)
    # Ritterschnitt through [4],[5],[6]:
    S5 = -P / 2                     # projection ⊥ to [4],[6]
    S4 = P * math.sqrt(2)           # ΣM_D = 0
    S6 = -P / math.sqrt(2)          # ΣM_E = 0

    # ── BSP 2: simply supported beam, triangular load 0→q0 ──────────────────
    q0  = float(rng.choice([2, 3, 4, 5, 6, 8]))
    AV2 = q0 * L / 6
    BV2 = q0 * L / 3
    # M(x) = -(q0/(6L))x³ + (q0 L/6)x
    def M2_bsp2(x): return -(q0 / (6 * L)) * x ** 3 + (q0 * L / 6) * x
    def V2_bsp2(x): return q0 * L / 6 - (q0 / (2 * L)) * x ** 2
    xmax2 = L / math.sqrt(3)
    Mmax2 = q0 * L ** 2 / (9 * math.sqrt(3))

    return dict(
        seed=seed, L=L, q=q, P=P, q0=q0,
        BV=BV, AH=AH, AV=AV, MA=MA,
        N1=N1, V1=V1, M1=M1,
        N2=N2, V2=V2, M2=M2,
        S4=S4, S5=S5, S6=S6, S8=S8, S9=S9,
        AV2=AV2, BV2=BV2, xmax2=xmax2, Mmax2=Mmax2,
        M2_bsp2=M2_bsp2, V2_bsp2=V2_bsp2,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 2.  NUMBER FORMATTING
# ══════════════════════════════════════════════════════════════════════════════

def fd(v: float, d: int = 2) -> str:
    """Format float (English dot)."""
    return f"{v:.{d}f}"

def fdg(v: float, d: int = 2) -> str:
    """Format float (German comma)."""
    return f"{v:.{d}f}".replace('.', '{,}')

def fsigned(v: float, d: int = 2) -> str:
    sign = '+' if v >= 0 else '-'
    return f"{sign}{abs(v):.{d}f}"


# ══════════════════════════════════════════════════════════════════════════════
# 3.  TIKZ: SYSTEM SKETCH  (BSP 1)
# ══════════════════════════════════════════════════════════════════════════════

TIKZ_SYSTEM_SKETCH = r"""
\begin{center}
\begin{tikzpicture}[scale=3.2, >=stealth, line cap=round, line join=round,
    thick, font=\small]

  %--- Node coordinates (normalized: 1 unit = L) ----------------------------
  \coordinate (A)   at (0.00, 0.00);
  \coordinate (C)   at (1.00, 0.00);
  \coordinate (G)   at (2.00, 0.00);
  \coordinate (D)   at (1.00,-0.50);
  \coordinate (E)   at (1.50,-0.50);
  \coordinate (Fnd) at (1.50,-1.00);
  \coordinate (B)   at (2.00,-1.00);

  %--- Fixed support (Einspannung) at A ------------------------------------
  \fill[pattern=north east lines, pattern color=black!55]
        (-0.14,-0.22) rectangle (0.00, 0.22);
  \draw[very thick] (0,-0.22) -- (0, 0.22);

  %--- Beam members [1] and [2] --------------------------------------------
  \draw[very thick] (A) -- (G);

  %--- Truss members -------------------------------------------------------
  \draw (C) -- (D);         % [3]
  \draw (C) -- (E);         % [4]
  \draw (D) -- (E);         % [5]
  \draw (D) -- (Fnd);       % [6]
  \draw (E) -- (Fnd);       % [7]
  \draw (E) -- (B);         % [8]
  \draw (Fnd) -- (B);       % [9]

  %--- Hinge at C (open circle) -------------------------------------------
  \filldraw[fill=white, draw=black, thin] (C) circle (1.3pt);

  %--- Roller support at B (verschiebliches Lager, vertical reaction) ------
  \draw (B) -- ++(0.09,-0.13) -- ++(-0.18, 0) -- cycle;
  \foreach \dx in {-0.09, -0.03, 0.03, 0.09}
    \filldraw[fill=white, draw=black, thin]
              ($(B)+(\dx,-0.13)$) circle (1.1pt);
  \draw[thick] ($(B)+(-0.13,-0.16)$) -- ++(0.26, 0);
  \fill[pattern=north east lines, pattern color=black!40]
       ($(B)+(-0.13,-0.19)$) rectangle ++(0.26,-0.05);

  %--- Distributed load q (downward arrows above beam) --------------------
  \foreach \xx in {0.10,0.30,0.50,0.70,0.90,1.10,1.30,1.50,1.70,1.90}
    \draw[->, thin, blue!75!black] (\xx, 0.32) -- (\xx, 0.04);
  \draw[thin, blue!75!black] (0.05, 0.32) -- (1.95, 0.32);
  \node[blue!75!black, right, inner sep=1pt] at (1.97, 0.32) {$q$};

  %--- Point load P at D (horizontal, rightward) --------------------------
  \draw[->, very thick, red!70!black]
        ($(D)+(-0.48,0)$) -- ($(D)+(-0.06,0)$);
  \node[red!70!black, left, inner sep=1pt] at ($(D)+(-0.50,0)$) {$P$};

  %--- Node labels ---------------------------------------------------------
  \node[left,  xshift=-2pt] at (A)   {\textbf{A}};
  \node[above, yshift= 3pt] at (C)   {\textbf{C}};
  \node[above right]        at (G)   {\textbf{G}};
  \node[left,  xshift=-2pt] at (D)   {\textbf{D}};
  \node[above right]        at (E)   {\textbf{E}};
  \node[right, xshift= 2pt] at (Fnd) {\textbf{F}};
  \node[right, xshift= 2pt] at (B)   {\textbf{B}};

  %--- Member labels -------------------------------------------------------
  \node[above]        at (0.50, 0.01) {[1]};
  \node[above]        at (1.50, 0.01) {[2]};
  \node[left]         at (1.00,-0.25) {[3]};
  \node[above right, xshift=-1pt] at (1.23,-0.23) {[4]};
  \node[above]        at (1.25,-0.50) {[5]};
  \node[below left, xshift=1pt]   at (1.23,-0.77) {[6]};
  \node[right]        at (1.50,-0.75) {[7]};
  \node[above right, xshift=-1pt] at (1.73,-0.72) {[8]};
  \node[below]        at (1.75,-1.00) {[9]};

  %--- Dimension lines -----------------------------------------------------
  \draw[<->, thin, gray] (0.00,-1.35) -- (1.00,-1.35)
        node[midway, below, font=\footnotesize] {$L$};
  \draw[<->, thin, gray] (1.00,-1.35) -- (1.50,-1.35)
        node[midway, below, font=\footnotesize] {$L/2$};
  \draw[<->, thin, gray] (1.50,-1.35) -- (2.00,-1.35)
        node[midway, below, font=\footnotesize] {$L/2$};
  \draw[<->, thin, gray] (2.30, 0.00) -- (2.30,-0.50)
        node[midway, right, font=\footnotesize] {$L/2$};
  \draw[<->, thin, gray] (2.30,-0.50) -- (2.30,-1.00)
        node[midway, right, font=\footnotesize] {$L/2$};

\end{tikzpicture}
\end{center}
"""


# ══════════════════════════════════════════════════════════════════════════════
# 4.  TIKZ: BSP 2 BEAM SKETCH
# ══════════════════════════════════════════════════════════════════════════════

TIKZ_BSP2_SKETCH = r"""
\begin{center}
\begin{tikzpicture}[scale=3.0, >=stealth, thick, font=\small]

  \coordinate (A) at (0,0);
  \coordinate (B) at (1,0);

  %--- Beam ----------------------------------------------------------------
  \draw[very thick] (A) -- (B);

  %--- Pin support at A ----------------------------------------------------
  \draw (A) -- ++( 0.08,-0.13) -- ++(-0.16, 0) -- cycle;
  \draw[thick] ($(A)+(-0.15,-0.13)$) -- ++(0.30, 0);
  \fill[pattern=north east lines, pattern color=black!40]
       ($(A)+(-0.15,-0.16)$) rectangle ++(0.30,-0.05);

  %--- Roller support at B -------------------------------------------------
  \draw (B) -- ++(0.08,-0.13) -- ++(-0.16, 0) -- cycle;
  \foreach \dx in {-0.07, -0.01, 0.05}
    \filldraw[fill=white, draw=black, thin]
              ($(B)+(\dx,-0.13)$) circle (1.0pt);
  \draw[thick] ($(B)+(-0.12,-0.16)$) -- ++(0.24, 0);

  %--- Triangular load (0 at A, q0 at B) -----------------------------------
  \draw[blue!75!black] (A) -- ++(0, 0.55); % left edge (zero)
  \foreach \xx in {0.12, 0.25, 0.38, 0.50, 0.63, 0.75, 0.88, 1.00}
    \draw[->, thin, blue!75!black] (\xx, {0.55*\xx}) -- (\xx, 0.03);
  \draw[blue!75!black] (0,0) -- (0, 0.55) -- (1, 0.55);
  \node[blue!75!black, right, inner sep=1pt] at (1.01, 0.55) {$q_0$};
  \node[blue!75!black, left,  inner sep=1pt] at (-0.01, 0)   {$0$};

  %--- Node labels ---------------------------------------------------------
  \node[above left]  at (A) {\textbf{A}};
  \node[above right] at (B) {\textbf{B}};

  %--- Support reaction labels ---------------------------------------------
  \draw[->, thick, black!70]  ($(A)+(0,-0.28)$) -- ++(0, 0.22)
        node[right, font=\footnotesize] {$A_v = \frac{1}{6}q_0 L$};
  \draw[->, thick, black!70]  ($(B)+(0,-0.28)$) -- ++(0, 0.22)
        node[right, font=\footnotesize] {$B_v = \frac{1}{3}q_0 L$};

  %--- Dimension -----------------------------------------------------------
  \draw[<->, thin, gray] (0,-0.50) -- (1,-0.50)
        node[midway, below, font=\footnotesize] {$L$};

\end{tikzpicture}
\end{center}
"""


# ══════════════════════════════════════════════════════════════════════════════
# 5.  TIKZ: M, V, N SOLUTION DIAGRAMS  (BSP 1)
# ══════════════════════════════════════════════════════════════════════════════

def _coords(func, x0: float, x1: float, n: int = 40) -> str:
    """Compute TikZ coordinate string for a function on [x0, x1]."""
    pts = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
    return ' '.join(f"({x:.5f},{func(x):.5f})" for x in pts)


def tikz_mvn_diagrams(p: dict) -> str:
    L  = p['L']
    q  = p['q']
    P  = p['P']
    AV = p['AV']
    MA = p['MA']
    N1 = p['N1']
    V1 = p['V1']
    M1 = p['M1']
    V2 = p['V2']
    M2 = p['M2']

    # ── Evaluate at key points ───────────────────────────────────────────────
    m1_A  = M1(0)      # = -MA  (negative, hogging)
    m1_C  = M1(L)      # = -q L²/2
    m2_C  = M2(0)      # = same as m1_C (continuity of M at hinge C)
    m2_G  = M2(L)      # = 0
    v1_A  = V1(0)      # = AV
    v1_C  = V1(L)      # just before C (from left)
    v2_C  = V2(0)      # just after C (from right, after jump -P/2)
    v2_G  = V2(L)      # = 0
    n1_val = N1(0)     # = P  (tension, constant in [1])

    # ── Scale factors ────────────────────────────────────────────────────────
    # x: normalized 0..2 (2 units = 2L), y: raw values (kNm or kN)
    # We scale y so that max absolute value maps to 0.9 units in TikZ.
    # With xscale=3 each unit = 3 cm, so 0.9 units ≈ 2.7 cm height.
    M_max   = max(abs(m1_A), abs(m1_C), 1e-6)
    V_max   = max(abs(v1_A), abs(v1_C), abs(v2_C), 1e-6)
    N_max   = max(abs(n1_val), 1e-6)
    M_scale = M_max / 0.75
    V_scale = V_max / 0.70
    N_scale = N_max / 0.65

    # ── Coordinate generators ────────────────────────────────────────────────
    # In all diagrams: x-axis goes left→right (A at 0, C at 1, G at 2)
    # On the tension side: negative M → plotted above baseline (+y)

    # M(x) coordinates (plotted: y = -M / M_scale → tension side up)
    def mplot1(x):   return -M1(x) / M_scale          # x in [0,L], tikz-x = x/L
    def mplot2(xn):  return -M2(xn*L) / M_scale       # xn = x/L, tikz-x = 1+xn

    # V(x) coordinates (positive V: plotted below baseline here, standard)
    def vplot1(x):   return V1(x) / V_scale
    def vplot2(xn):  return V2(xn*L) / V_scale

    # N(x) coordinates (positive = tension, drawn below beam axis)
    def nplot1(x):   return N1(x) / N_scale

    # Build coordinate strings (normalized tikz-x: 0..1 for [1], 1..2 for [2])
    xs1 = [i / 30 for i in range(31)]       # 0..1 step 1/30
    xs2 = [1 + i / 30 for i in range(31)]   # 1..2

    def coord_str_fn(tikzx_list, yfunc):
        return ' '.join(f"({tx:.5f},{yfunc(tx):.5f})" for tx in tikzx_list)

    m1_str = coord_str_fn(xs1, lambda tx: -M1(tx * L) / M_scale)
    m2_str = coord_str_fn(xs2, lambda tx: -M2((tx - 1) * L) / M_scale)
    v1_str = coord_str_fn(xs1, lambda tx:  V1(tx * L) / V_scale)
    v2_str = coord_str_fn(xs2, lambda tx:  V2((tx - 1) * L) / V_scale)

    # Value labels
    def lbl(v, d=1): return fd(v, d)

    # M labels
    lbl_m1A = lbl(m1_A)
    lbl_m1C = lbl(m1_C)
    lbl_v1A = lbl(v1_A)
    lbl_v1C = lbl(v1_C)
    lbl_v2C = lbl(v2_C)
    lbl_n   = lbl(n1_val)

    # Plotted y values (for label placement)
    pm1A = -m1_A / M_scale
    pm1C = -m1_C / M_scale
    pv1A =  v1_A / V_scale
    pv1C =  v1_C / V_scale
    pv2C =  v2_C / V_scale
    pn   =  n1_val / N_scale

    return rf"""
%─────────────────────────────────────────────────────────────────────────────
\subsubsection*{{Schnittgrößenverläufe (auf der Zugseite; neg.\,M nach oben)}}

\begin{{center}}
\begin{{tikzpicture}}[xscale=3.2, yscale=3.2, >=stealth, thick, font=\small]

  %--- Axis ticks and node labels for ALL diagrams -------------------------
  % We stack 3 diagrams vertically: M at y-offset=0, V at y-offset=-2, N at y-offset=-4

  %====================================================================
  % MOMENT  M(x)
  %====================================================================
  \begin{{scope}}[yshift= 0cm]
    % Baseline
    \draw[->] (-0.1, 0) -- (2.15, 0) node[right] {{$x$}};
    \node[left] at (0,0)   {{A}};
    \node[above] at (1,0)  {{C}};
    \node[right] at (2,0)  {{G}};
    \draw[thin, dashed] (1,0) -- (1, {pm1C:.4f});

    % M in Stab [1]: filled area (tension side = above)
    \filldraw[fill=blue!15, draw=blue!60!black, thick]
      (0,0) -- plot coordinates {{ {m1_str} }} -- (1,0) -- cycle;

    % M in Stab [2]: filled area
    \filldraw[fill=blue!15, draw=blue!60!black, thick]
      (1,0) -- plot coordinates {{ {m2_str} }} -- (2,0) -- cycle;

    % Value labels
    \node[right, blue!70!black] at (0, {pm1A:.4f})
          {{$M={lbl_m1A}$\,kNm}};
    \node[right, blue!70!black] at (1, {pm1C:.4f})
          {{$M={lbl_m1C}$\,kNm}};
    \node[above] at (1,-0.05) {{\footnotesize C}};

    % Axis label
    \node[rotate=90, blue!70!black] at (-0.35, {pm1A/2:.4f}) {{$M(x)$}};
  \end{{scope}}

  %====================================================================
  % SHEAR FORCE  V(x)
  %====================================================================
  \begin{{scope}}[yshift=-2.8cm]
    \draw[->] (-0.1, 0) -- (2.15, 0) node[right] {{$x$}};
    \node[left]  at (0,0)  {{A}};
    \node[above] at (1,-0.02) {{C}};
    \node[right] at (2,0)  {{G}};

    % V in Stab [1]
    \filldraw[fill=red!15, draw=red!60!black, thick]
      (0,0) -- plot coordinates {{ {v1_str} }} -- (1,0) -- cycle;

    % V in Stab [2]
    \filldraw[fill=red!15, draw=red!60!black, thick]
      (1,0) -- plot coordinates {{ {v2_str} }} -- (2,0) -- cycle;

    % Jump at C (vertical dashed line)
    \draw[dashed, thin] (1, {pv1C:.4f}) -- (1, {pv2C:.4f});

    % Labels
    \node[right, red!70!black] at (0,  {pv1A:.4f}) {{$V={lbl_v1A}$\,kN}};
    \node[right, red!70!black] at (1,  {pv1C:.4f}) {{$V={lbl_v1C}$\,kN}};
    \node[left,  red!70!black] at (1,  {pv2C:.4f}) {{$V={lbl_v2C}$\,kN}};
    \node[rotate=90, red!70!black] at (-0.35, {pv1A/2:.4f}) {{$V(x)$}};
  \end{{scope}}

  %====================================================================
  % AXIAL FORCE  N(x)
  %====================================================================
  \begin{{scope}}[yshift=-5.6cm]
    \draw[->] (-0.1, 0) -- (2.15, 0) node[right] {{$x$}};
    \node[left]  at (0,0)  {{A}};
    \node[above] at (1,-0.02) {{C}};
    \node[right] at (2,0)  {{G}};

    % N in Stab [1]: constant positive (tension, draw below baseline)
    \filldraw[fill=green!15, draw=green!50!black, thick]
      (0,0) -- (0,-{pn:.4f}) -- (1,-{pn:.4f}) -- (1,0) -- cycle;

    % N in Stab [2]: zero
    % (nothing to draw)
    \draw[green!50!black, thick] (1,0) -- (2,0);

    % Labels
    \node[right, green!40!black] at (0,  -{pn:.4f})
          {{$N=+{lbl_n}$\,kN\,(Zug)}};
    \node[rotate=90, green!40!black] at (-0.35, -{pn/2:.4f}) {{$N(x)$}};
  \end{{scope}}

\end{{tikzpicture}}
\end{{center}}
"""


# ══════════════════════════════════════════════════════════════════════════════
# 6.  TIKZ: BSP 2 SOLUTION DIAGRAMS
# ══════════════════════════════════════════════════════════════════════════════

def tikz_bsp2_diagrams(p: dict) -> str:
    L     = p['L']
    q0    = p['q0']
    xmax2 = p['xmax2']
    Mmax2 = p['Mmax2']
    AV2   = p['AV2']
    BV2   = p['BV2']
    M_fn  = p['M2_bsp2']
    V_fn  = p['V2_bsp2']

    V_max = max(abs(AV2), abs(BV2))
    M_max = max(abs(Mmax2), 1e-9)
    V_scale = V_max / 0.55
    M_scale = M_max / 0.55

    # normalized x runs 0..1 (represents 0..L)
    xmax_n = xmax2 / L

    xs = [i / 40 for i in range(41)]
    v_str = ' '.join(f"({x:.5f},{V_fn(x*L)/V_scale:.5f})" for x in xs)
    m_str = ' '.join(f"({x:.5f},{M_fn(x*L)/M_scale:.5f})" for x in xs)

    lbl_AV2   = fd(AV2, 2)
    lbl_BV2   = fd(BV2, 2)
    lbl_Mmax2 = fd(Mmax2, 4)
    lbl_xmax2 = fd(xmax2, 4)

    pAV2  =  AV2  / V_scale
    pBV2  = -BV2  / V_scale
    pMmax = Mmax2 / M_scale
    pxmax = xmax_n

    return rf"""
\begin{{center}}
\begin{{tikzpicture}}[xscale=3.5, yscale=3.5, >=stealth, thick, font=\small]

  %====================================================================
  % SHEAR FORCE  V(x)
  %====================================================================
  \begin{{scope}}[yshift=0cm]
    \draw[->] (-0.05,0) -- (1.1,0) node[right]{{$x$}};
    \node[left]  at (0,0)  {{A}};
    \node[right] at (1,0)  {{B}};

    \filldraw[fill=red!15, draw=red!60!black, thick]
      (0,0) -- plot coordinates {{ {v_str} }} -- (1,0) -- cycle;

    \node[right, red!70!black] at (0,  {pAV2:.4f}) {{$+{lbl_AV2}$\,kN}};
    \node[right, red!70!black] at (1,  {pBV2:.4f}) {{$-{lbl_BV2}$\,kN}};
    \draw[thin,dashed,gray] ({pxmax:.4f},0) -- ({pxmax:.4f},{0:.4f});
    \node[above, gray, font=\footnotesize] at ({pxmax:.4f}, 0)
          {{$x_{{max}}=\tfrac{{L}}{{\sqrt{{3}}}}$}};
    \node[rotate=90, red!70!black] at (-0.22, 0.1) {{$V(x)$}};
  \end{{scope}}

  %====================================================================
  % MOMENT  M(x)
  %====================================================================
  \begin{{scope}}[yshift=-1.9cm]
    \draw[->] (-0.05,0) -- (1.1,0) node[right]{{$x$}};
    \node[left]  at (0,0) {{A}};
    \node[right] at (1,0) {{B}};

    \filldraw[fill=blue!15, draw=blue!60!black, thick]
      (0,0) -- plot coordinates {{ {m_str} }} -- (1,0) -- cycle;

    % Max moment marker
    \draw[thin, dashed, gray] ({pxmax:.4f}, 0) -- ({pxmax:.4f}, {pMmax:.4f});
    \node[below, blue!70!black] at ({pxmax:.4f}, {pMmax:.4f})
          {{$M_{{max}}\approx {lbl_Mmax2}$\,kNm}};
    \node[rotate=90, blue!70!black] at (-0.22, {pMmax/2:.4f}) {{$M(x)$}};
  \end{{scope}}

\end{{tikzpicture}}
\end{{center}}
"""


# ══════════════════════════════════════════════════════════════════════════════
# 7.  LATEX PREAMBLE
# ══════════════════════════════════════════════════════════════════════════════

def preamble(lang: str = 'de') -> str:
    babel = 'ngerman' if lang == 'de' else 'english'
    return rf"""\documentclass[a4paper,11pt]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage[T1]{{fontenc}}
\usepackage[{babel}]{{babel}}
\usepackage{{lmodern}}
\usepackage{{microtype}}
\usepackage{{amsmath,amssymb,bm,mathtools}}
\usepackage{{geometry}}
\geometry{{a4paper, left=2.4cm, right=2.4cm, top=2.0cm, bottom=2.2cm}}
\usepackage{{booktabs,multirow,array}}
\usepackage{{xcolor}}
\definecolor{{bokug}}{{RGB}}{{0,135,60}}
\usepackage{{tikz}}
\usetikzlibrary{{patterns,arrows.meta,calc,decorations.pathmorphing,
                 decorations.markings}}
\usepackage{{fancyhdr}}
\pagestyle{{fancy}}
\renewcommand{{\headrulewidth}}{{0.4pt}}
\renewcommand{{\footrulewidth}}{{0.4pt}}
\usepackage{{enumitem}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{4pt}}
"""


# ══════════════════════════════════════════════════════════════════════════════
# 8.  EXAM SHEET  (Angabe)  –  GERMAN
# ══════════════════════════════════════════════════════════════════════════════

def make_exam_de(p: dict, group: str, date_str: str, semester: str) -> str:
    L  = p['L']; q  = p['q']; P  = p['P']; q0 = p['q0']
    lL  = fd(L,  1 if L != int(L) else 0)
    lq  = fd(q,  0)
    lP  = fd(P,  0)
    lq0 = fd(q0, 0)

    header = rf"""
\fancyhead[L]{{\small VU Mechanik -- LAWI 100515 (PI)\quad {semester}}}
\fancyhead[R]{{\small 2.~Übungsklausur\quad {date_str}\quad Gruppe~{group}}}
\fancyfoot[C]{{\small {date_str} \qquad Mechanik VU -- LAWI 100515 (PI) \qquad {semester}}}
\fancyfoot[R]{{\small Seite~\thepage}}
"""

    coverpage = rf"""
\begin{{center}}
  {{\LARGE\bfseries VU MECHANIK -- LAWI 100515 (PI)\\[4pt]
  {semester}}}\\[10pt]
  {{\Large\bfseries 2.~Übungsklausur}}\\[4pt]
  {{\large {date_str} \quad GRUPPE~{group}}}
\end{{center}}

\vspace{{6pt}}
\begin{{center}}
\begin{{tabular}}{{|p{{4.5cm}}|p{{8cm}}|}}
\hline
Name: & \\[8pt] \hline
Matrikelnummer: & \\[8pt] \hline
Studienkennzahl: & \\[8pt] \hline
Anmerkungen & \\[14pt] \hline
\multicolumn{{1}}{{|l|}}{{Ergebnis}} & \hspace{{3cm}}\_\_\_/100 \\[6pt] \hline
\end{{tabular}}
\end{{center}}

\vspace{{6pt}}
\begin{{tabular}}{{lcc}}
\toprule
\textbf{{Aufgaben}} & \textbf{{Mögliche Punkte}} & \textbf{{Erreichte Punkte}} \\
\midrule
1)\;BSP 1 -- Schnittgrößenermittlung  & 40 & \\
2)\;BSP 1 -- Fachwerk                 & 30 & \\
3)\;BSP 2                              & 30 & \\
\bottomrule
\end{{tabular}}

\medskip
\textbf{{Arbeitszeit:}} 90~min\quad
\textbf{{Positive Beurteilung:}} $\geq 50\,\%$

\textbf{{Erlaubte Hilfsmittel:}} Formelsammlung (boku-learn), Taschenrechner, Geodreieck, Zirkel.
Kein Bleistift, kein Rotstift, kein selbst mitgebrachtes Papier.
"""

    bsp1 = rf"""
\newpage
\section*{{1.~Beispiel \hfill (70\,\%)}}

\textbf{{Gegeben}} ist das nachstehend abgebildete ebene statische System.
Die Abmessungen und Systemkennwerte sind der Systemskizze zu entnehmen.
Belastet wird dieses Tragwerk durch eine auf die Stäbe [1] und [2] wirkende
\textbf{{\textcolor{{blue!70!black}}{{Gleichlast~$q$}}}} sowie eine am Knoten~D
angreifende \textbf{{\textcolor{{red!70!black}}{{Einzelkraft~$P$}}}}.

\medskip
\begin{{tabular}}{{|c|c|c|}}
\hline
$L = {lL}$\,m & $q = {lq}$\,kN/m & $P = {lP}$\,kN \\
\hline
\end{{tabular}}

{TIKZ_SYSTEM_SKETCH}

\textbf{{Gesucht:}}
\begin{{enumerate}}[leftmargin=*, label=\arabic*.]
  \item Überprüfen Sie die statische Bestimmtheit des Systems.
  \item Ermitteln Sie die Auflagerreaktionen \textbf{{allgemein als Funktionen von $q$, $P$ und $L$}}.
        Zeichnen Sie die Reaktionen in die Systemskizze ein.
  \item Werten Sie die Auflagerreaktionen für die gegebenen Systemkennwerte aus:
        \[
          A_V = \hspace{{2.5cm}}
          A_H = \hspace{{2.5cm}}
          M_A = \hspace{{2.5cm}}
          B_V = \hspace{{2.5cm}}
        \]
  \item Ermitteln Sie die Schnittgrößen $M(x)$, $V(x)$ und $N(x)$ in den Stäben [1] und [2]
        \textbf{{allgemein als Funktionen von $q$, $P$ und $L$}}.
        Definieren Sie jeweils den Wertebereich von~$x$.
        Werten Sie die Funktionen am Stabanfang und -ende aus:

        \medskip
        \begin{{tabular}}{{l cccccc}}
        \toprule
         & \multicolumn{{3}}{{c}}{{\textbf{{Stabanfang}}}} & \multicolumn{{3}}{{c}}{{\textbf{{Stabende}}}} \\
        \cmidrule(lr){{2-4}}\cmidrule(lr){{5-7}}
         & $M$\,[kNm] & $V$\,[kN] & $N$\,[kN]
         & $M$\,[kNm] & $V$\,[kN] & $N$\,[kN] \\
        \midrule
        Stab [1] & & & & & & \\[6pt]
        Stab [2] & & & & & & \\
        \bottomrule
        \end{{tabular}}

  \item Stellen Sie die gesamten Schnittgrößenverläufe $M(x)$, $V(x)$ und $N(x)$ graphisch dar
        (mit Zahlenwerten in den charakteristischen Punkten).

  \item Berechnen Sie die Stabkräfte $S_8$ und $S_9$ mittels \textbf{{Rundschnitt am Knoten~B}}
        \textbf{{allgemein als Funktion von $P$}}:
        \[
          S_8 = \hspace{{3cm}} S_9 = \hspace{{3cm}}
        \]

  \item Berechnen Sie die Stabkräfte $S_4$, $S_5$ und $S_6$ mittels \textbf{{Ritterschnitt}}
        \textbf{{allgemein als Funktion von $P$}}:
        \[
          S_4 = \hspace{{2.5cm}} S_5 = \hspace{{2.5cm}} S_6 = \hspace{{2.5cm}}
        \]
\end{{enumerate}}
"""

    bsp2 = rf"""
\newpage
\section*{{2.~Beispiel \hfill (30\,\%)}}

\textbf{{Gegeben}} ist der nachstehend abgebildete Einfeldträger (Spannweite~$L$)
mit einer Dreieckslast (0 bei~A bis $q_0$ bei~B).
Die Auflagerkräfte betragen $A_v = \tfrac{{1}}{{6}}q_0 L$ und $B_v = \tfrac{{1}}{{3}}q_0 L$.
Der Momentenverlauf ergibt sich zu:
\[
  M(x) = -\frac{{q_0}}{{6L}}\,x^3 + \frac{{q_0 L}}{{6}}\,x
  \qquad (0 \le x \le L)
\]

\begin{{tabular}}{{|c|c|}}
\hline
$L = {lL}$\,m & $q_0 = {lq0}$\,kN/m \\
\hline
\end{{tabular}}

{TIKZ_BSP2_SKETCH}

\textbf{{Gesucht:}}
\begin{{enumerate}}[leftmargin=*, label=\arabic*.]
  \item Bestimmen Sie die Querkraft $V(x)$ als Funktion von $x$.
  \item Ermitteln Sie die Position $x_{{\max}}$, an der das Moment maximal wird.
  \item Berechnen Sie das maximale Moment $M_{{\max}}$.
  \item Stellen Sie $V(x)$ und $M(x)$ graphisch dar (mit charakteristischen Werten).
\end{{enumerate}}
"""

    doc = preamble('de') + r"\begin{document}" + "\n"
    doc += header + coverpage + bsp1 + bsp2
    doc += r"\end{document}" + "\n"
    return doc


# ══════════════════════════════════════════════════════════════════════════════
# 9.  EXAM SHEET  –  ENGLISH
# ══════════════════════════════════════════════════════════════════════════════

def make_exam_en(p: dict, group: str, date_str: str, semester: str) -> str:
    L  = p['L']; q  = p['q']; P  = p['P']; q0 = p['q0']
    lL  = fd(L,  1 if L != int(L) else 0)
    lq  = fd(q,  0)
    lP  = fd(P,  0)
    lq0 = fd(q0, 0)

    header = rf"""
\fancyhead[L]{{\small VU Mechanics -- LAWI 100515 (PI)\quad {semester}}}
\fancyhead[R]{{\small 2nd Exercise Exam\quad {date_str}\quad Group~{group}}}
\fancyfoot[C]{{\small {date_str} \qquad Mechanics VU -- LAWI 100515 (PI) \qquad {semester}}}
\fancyfoot[R]{{\small Page~\thepage}}
"""

    coverpage = rf"""
\begin{{center}}
  {{\LARGE\bfseries VU MECHANICS -- LAWI 100515 (PI)\\[4pt]
  {semester}}}\\[10pt]
  {{\Large\bfseries 2nd Exercise Exam}}\\[4pt]
  {{\large {date_str} \quad GROUP~{group}}}
\end{{center}}

\vspace{{6pt}}
\begin{{center}}
\begin{{tabular}}{{|p{{4.5cm}}|p{{8cm}}|}}
\hline
Name: & \\[8pt] \hline
Student ID number: & \\[8pt] \hline
Study program code: & \\[8pt] \hline
Notes & \\[14pt] \hline
\multicolumn{{1}}{{|l|}}{{Result}} & \hspace{{3cm}}\_\_\_/100 \\[6pt] \hline
\end{{tabular}}
\end{{center}}

\vspace{{6pt}}
\begin{{tabular}}{{lcc}}
\toprule
\textbf{{Tasks}} & \textbf{{Possible Points}} & \textbf{{Achieved Points}} \\
\midrule
1)\;Task 1 -- Section Forces and Moments & 40 & \\
2)\;Task 1 -- Truss System               & 30 & \\
3)\;Task 2                               & 30 & \\
\bottomrule
\end{{tabular}}

\medskip
\textbf{{Working Time:}} 90~min\quad
\textbf{{Passing Grade:}} $\geq 50\,\%$

\textbf{{Permitted Aids:}} Formula sheet (boku-learn), calculator, set square, compass.
No pencil, no red pen, no own paper.
"""

    bsp1 = rf"""
\newpage
\section*{{1.~Task \hfill (70\,\%)}}

\textbf{{Given}} is the planar static system shown below.
Dimensions and system parameters are given in the sketch.
The structure is loaded by a \textbf{{\textcolor{{blue!70!black}}{{uniformly distributed load~$q$}}}}
acting on beams [1] and [2], and a
\textbf{{\textcolor{{red!70!black}}{{concentrated load~$P$}}}} at truss node~D.

\medskip
\begin{{tabular}}{{|c|c|c|}}
\hline
$L = {lL}$\,m & $q = {lq}$\,kN/m & $P = {lP}$\,kN \\
\hline
\end{{tabular}}

{TIKZ_SYSTEM_SKETCH}

\textbf{{Tasks:}}
\begin{{enumerate}}[leftmargin=*, label=\arabic*.]
  \item Check whether the system is statically determinate.
  \item Determine the support reactions \textbf{{in general form as functions of $q$, $P$, and $L$}}.
        Draw the reactions into the system sketch.
  \item Evaluate the support reactions for the given parameters:
        \[
          A_V = \hspace{{2.5cm}}
          A_H = \hspace{{2.5cm}}
          M_A = \hspace{{2.5cm}}
          B_V = \hspace{{2.5cm}}
        \]
  \item Determine the section forces $M(x)$, $V(x)$, and $N(x)$ in beams [1] and [2]
        \textbf{{in general form as functions of $q$, $P$, and $L$}}.
        Define the range of the running variable~$x$.
        Evaluate the functions at the beam start and end:

        \medskip
        \begin{{tabular}}{{l cccccc}}
        \toprule
         & \multicolumn{{3}}{{c}}{{\textbf{{Beam start}}}} & \multicolumn{{3}}{{c}}{{\textbf{{Beam end}}}} \\
        \cmidrule(lr){{2-4}}\cmidrule(lr){{5-7}}
         & $M$\,[kNm] & $V$\,[kN] & $N$\,[kN]
         & $M$\,[kNm] & $V$\,[kN] & $N$\,[kN] \\
        \midrule
        Beam [1] & & & & & & \\[6pt]
        Beam [2] & & & & & & \\
        \bottomrule
        \end{{tabular}}

  \item Draw the distributions $M(x)$, $V(x)$, and $N(x)$ and mark the characteristic values.

  \item Calculate the axial forces $S_8$ and $S_9$ using a \textbf{{circular cut (Rundschnitt)
        at node~B}}, in general form as a function of~$P$:
        \[
          S_8 = \hspace{{3cm}} S_9 = \hspace{{3cm}}
        \]

  \item Calculate the axial forces $S_4$, $S_5$, and $S_6$ using \textbf{{Ritter's cut
        (Ritterschnitt)}}, in general form as a function of~$P$:
        \[
          S_4 = \hspace{{2.5cm}} S_5 = \hspace{{2.5cm}} S_6 = \hspace{{2.5cm}}
        \]
\end{{enumerate}}
"""

    bsp2 = rf"""
\newpage
\section*{{2.~Task \hfill (30\,\%)}}

\textbf{{Given}} is a simply supported beam (span~$L$)
with a triangular load (0 at~A, $q_0$ at~B).
The support reactions are $A_v = \tfrac{{1}}{{6}}q_0 L$ and $B_v = \tfrac{{1}}{{3}}q_0 L$.
The bending moment distribution is:
\[
  M(x) = -\frac{{q_0}}{{6L}}\,x^3 + \frac{{q_0 L}}{{6}}\,x
  \qquad (0 \le x \le L)
\]

\begin{{tabular}}{{|c|c|}}
\hline
$L = {lL}$\,m & $q_0 = {lq0}$\,kN/m \\
\hline
\end{{tabular}}

{TIKZ_BSP2_SKETCH}

\textbf{{Tasks:}}
\begin{{enumerate}}[leftmargin=*, label=\arabic*.]
  \item Determine the shear force $V(x)$ as a function of~$x$.
  \item Find the position $x_{{\max}}$ along the beam where the moment is maximum.
  \item Calculate the corresponding maximum moment $M_{{\max}}$.
  \item Sketch the distributions of $V(x)$ and $M(x)$ with all characteristic values.
\end{{enumerate}}
"""

    doc = preamble('en') + r"\begin{document}" + "\n"
    doc += header + coverpage + bsp1 + bsp2
    doc += r"\end{document}" + "\n"
    return doc


# ══════════════════════════════════════════════════════════════════════════════
# 10. SOLUTION  (Musterlösung)  –  GERMAN
# ══════════════════════════════════════════════════════════════════════════════

def make_sol_de(p: dict, group: str, date_str: str, semester: str) -> str:
    L  = p['L']; q = p['q']; P = p['P']; q0 = p['q0']
    BV = p['BV']; AH = p['AH']; AV = p['AV']; MA = p['MA']
    S4 = p['S4']; S5 = p['S5']; S6 = p['S6']; S8 = p['S8']; S9 = p['S9']
    AV2 = p['AV2']; BV2 = p['BV2']; xmax2 = p['xmax2']; Mmax2 = p['Mmax2']

    lL  = fd(L,  1 if L != int(L) else 0)
    lq  = fd(q,  0)
    lP  = fd(P,  0)
    lq0 = fd(q0, 0)

    # Section-force table values
    M1s = fd(p['M1'](0));  V1s = fd(p['V1'](0));  N1s = fd(p['N1'](0))
    M1e = fd(p['M1'](L));  V1e = fd(p['V1'](L));  N1e = fd(p['N1'](L))
    M2s = fd(p['M2'](0));  V2s = fd(p['V2'](0));  N2s = fd(0.0)
    M2e = fd(p['M2'](L));  V2e = fd(p['V2'](L));  N2e = fd(0.0)

    # sign symbols
    def sgn(v): return '+' if v >= 0 else '-'
    def absf(v, d=2): return fd(abs(v), d)

    header = rf"""
\fancyhead[L]{{\small Musterlösung\quad VU Mechanik -- LAWI 100515 (PI)\quad {semester}}}
\fancyhead[R]{{\small 2.~Übungsklausur ({date_str})\quad Gruppe~{group}}}
\fancyfoot[C]{{\small Musterlösung}}
\fancyfoot[R]{{\small Seite~\thepage}}
"""

    sol = rf"""
\begin{{center}}
  {{\Large\bfseries Musterlösung}}\\[4pt]
  {{\large VU Mechanik -- LAWI 100515 (PI)\quad {semester}}}\\[2pt]
  {{\normalsize 2.~Übungsklausur ({date_str}) -- Gruppe~{group}}}\\[2pt]
  {{\normalsize \textbf{{Systemwerte:}} $L = {lL}$\,m,\quad $q = {lq}$\,kN/m,\quad $P = {lP}$\,kN}}
\end{{center}}

\section*{{1.~Beispiel \hfill (70\,\%)}}

{TIKZ_SYSTEM_SKETCH}

\subsection*{{1.1\quad Statische Bestimmtheit}}

Das Tragwerk besteht aus \textbf{{zwei starren Scheiben}}: dem Biegeträger A--C--G
(Stäbe~[1],\,[2]) und dem Fachwerk (Knoten C,D,E,F,B; Stäbe~[3]--[9]).

\textit{{Gesamtsystem:}} 2 Scheiben $\Rightarrow$ $2 \times 3 = 6$ Gleichgewichtsbedingungen.
Unbekannte: Auflager A (Einspannung) $= 3$, Auflager B (verschiebliches Lager) $= 1$,
Gelenkverbindung C zwischen Träger und Fachwerk $= 2$. Summe $= 6$.
\[
  n = \underbrace{{3}}_{{A}} + \underbrace{{1}}_{{B}} + \underbrace{{2}}_{{C}} - 2 \cdot 3
    = 6 - 6 = 0
  \quad\Rightarrow\quad \boxed{{n = 0: \text{{statisch bestimmt}}}}
\]

\subsection*{{1.2\quad Auflagerreaktionen (allgemein als Funktion von $q$, $P$, $L$)}}

\textbf{{Fachwerk als Teilsystem}}
(Gelenkskräfte $C_x$, $C_y$ vom Träger auf das Fachwerk; $B_V$ in B; $P$ in D):
\begin{{align*}}
  \sum M_C = 0:\quad & P \cdot \tfrac{{L}}{{2}} + B_V \cdot L = 0
    &&\Rightarrow\quad \boxed{{B_V = -\tfrac{{P}}{{2}}}} \\
  \sum F_x = 0:\quad & C_x + P = 0
    &&\Rightarrow\quad C_x = -P \\
  \sum F_y = 0:\quad & C_y + B_V = 0
    &&\Rightarrow\quad C_y = +\tfrac{{P}}{{2}}
\end{{align*}}

\textbf{{Gesamtsystem}} (Gleichlast $Q = q \cdot 2L$ mit Angriffspunkt $x = L$):
\begin{{align*}}
  \sum F_x = 0:\quad & A_H + P = 0
    &&\Rightarrow\quad \boxed{{A_H = -P}} \\
  \sum F_y = 0:\quad & A_V + B_V - 2qL = 0
    &&\Rightarrow\quad \boxed{{A_V = 2qL + \tfrac{{P}}{{2}}}} \\
  \sum M_A = 0:\quad & M_A - 2qL \cdot L + P\cdot\tfrac{{L}}{{2}} + B_V \cdot 2L = 0
    &&\Rightarrow\quad \boxed{{M_A = 2qL^2 + \tfrac{{PL}}{{2}}}}
\end{{align*}}

\subsection*{{1.3\quad Zahlenwerte}}

\begin{{center}}
\begin{{tabular}}{{cccc}}
\toprule
$A_V$ & $A_H$ & $M_A$ & $B_V$ \\
\midrule
$2qL + \tfrac{{P}}{{2}} = \mathbf{{{fd(AV, 2)}}}$\,kN
& $-P = \mathbf{{{fd(AH, 2)}}}$\,kN
& $2qL^2 + \tfrac{{PL}}{{2}} = \mathbf{{{fd(MA, 2)}}}$\,kNm
& $-\tfrac{{P}}{{2}} = \mathbf{{{fd(BV, 2)}}}$\,kN \\
\bottomrule
\end{{tabular}}
\end{{center}}

Vorzeichen: positiv $\uparrow$ für $A_V$, $B_V$; positiv $\rightarrow$ für $A_H$;
CCW für $M_A$. Negativ $\Rightarrow$ tatsächliche Richtung entgegengesetzt.

\textit{{Kontrolle}} $\sum M_B = 0$:
$M_A - A_H \cdot L - 2A_V \cdot L + 2qL^2 - \tfrac{{PL}}{{2}} = 0$\;
\checkmark

\subsection*{{1.4\quad Schnittgrößen in den Stäben [1] und [2]}}

Am Knoten C wirkt auf den Träger die Fachwerkkraft
$(-C_x,\,-C_y) = (+P,\,-\tfrac{{P}}{{2}})$:
$P$ nach rechts und $\tfrac{{P}}{{2}}$ nach unten.
Laufvariable $x$ jeweils ab Stabanfang.

\textbf{{Stab~[1] (A\,$\to$\,C), $0 \le x \le L$:}}
\begin{{align*}}
  N_1(x) &= P = \text{{const}} \\
  V_1(x) &= \Bigl(2qL + \tfrac{{P}}{{2}}\Bigr) - qx \\
  M_1(x) &= \Bigl(2qL + \tfrac{{P}}{{2}}\Bigr)x - \tfrac{{q}}{{2}}x^2
            - \Bigl(2qL^2 + \tfrac{{PL}}{{2}}\Bigr)
\end{{align*}}

\textbf{{Stab~[2] (C\,$\to$\,G), $0 \le x \le L$:}}
\begin{{align*}}
  N_2(x) &= 0 \\
  V_2(x) &= q(L - x) \\
  M_2(x) &= -\tfrac{{q}}{{2}}(L - x)^2
\end{{align*}}

Am Übergang C: Querkraftsprung $-\tfrac{{P}}{{2}}$ (vertikale Fachwerkkraft);
Normalkraftsprung $-P$ (horizontale Fachwerkkraft); Moment stetig, jedoch mit Knick.

\medskip
\begin{{center}}
\begin{{tabular}}{{l cccccc}}
\toprule
 & \multicolumn{{3}}{{c}}{{\textbf{{Stabanfang}}}} & \multicolumn{{3}}{{c}}{{\textbf{{Stabende}}}} \\
\cmidrule(lr){{2-4}}\cmidrule(lr){{5-7}}
 & $M$\,[kNm] & $V$\,[kN] & $N$\,[kN]
 & $M$\,[kNm] & $V$\,[kN] & $N$\,[kN] \\
\midrule
Stab~[1] (A$\to$C) & ${M1s}$ & ${V1s}$ & ${N1s}$ & ${M1e}$ & ${V1e}$ & ${N1e}$ \\[3pt]
Stab~[2] (C$\to$G) & ${M2s}$ & ${V2s}$ & ${N2s}$ & ${M2e}$ & ${V2e}$ & ${N2e}$ \\
\bottomrule
\end{{tabular}}
\end{{center}}

\subsection*{{1.5\quad Schnittgrößenverläufe}}

{tikz_mvn_diagrams(p)}

\subsection*{{1.6\quad Stabkräfte $S_8$ und $S_9$ -- Rundschnitt am Knoten B}}

Knoten B: Stab~[8] (B$\to$E, Richtung $\tfrac{{1}}{{\sqrt{{2}}}}(-1,+1)$),
Stab~[9] (B$\to$F, Richtung $(-1,\,0)$), Auflager $B_V = -\tfrac{{P}}{{2}}$.
\begin{{align*}}
  \sum F_y = 0:\quad & \tfrac{{S_8}}{{\sqrt{{2}}}} + B_V = 0
    &&\Rightarrow\quad S_8 = -\sqrt{{2}}\,B_V = \tfrac{{P}}{{\sqrt{{2}}}}
       &&\Rightarrow\quad \boxed{{S_8 = \tfrac{{P}}{{\sqrt{{2}}}} \approx {fd(S8, 2)}\,\text{{kN (Zug)}}}} \\
  \sum F_x = 0:\quad & -\tfrac{{S_8}}{{\sqrt{{2}}}} - S_9 = 0
    &&\Rightarrow\quad S_9 = -\tfrac{{S_8}}{{\sqrt{{2}}}} = -\tfrac{{P}}{{2}}
       &&\Rightarrow\quad \boxed{{S_9 = -\tfrac{{P}}{{2}} = {fd(S9, 2)}\,\text{{kN (Druck)}}}}
\end{{align*}}

\subsection*{{1.7\quad Stabkräfte $S_4$, $S_5$, $S_6$ -- Ritterschnitt}}

Schnitt durch [4],[5],[6]; rechter Teil \{{E,F,B\}} ($B_V = -\tfrac{{P}}{{2}}$ äußerlich; $P$ liegt im linken Teil).
Stäbe~[4] (C--E) und [6] (D--F): je Neigung $-45^\circ$; Stab~[5] (D--E): horizontal.

\textbf{{$S_5$}} -- Projektion aller Kräfte des rechten Teils auf $\tfrac{{1}}{{\sqrt{{2}}}}(1,1)$
(senkrecht zu [4] und [6], eliminiert $S_4$ und $S_6$):
\[
  -\tfrac{{S_5}}{{\sqrt{{2}}}} - \tfrac{{P}}{{2\sqrt{{2}}}} = 0
  \quad\Rightarrow\quad \boxed{{S_5 = -\tfrac{{P}}{{2}} = {fd(S5, 2)}\,\text{{kN (Druck)}}}}
\]

\textbf{{$S_4$}} -- Momentensumme um D
([5] und [6] laufen durch D; nur $S_4$ und $B_V$ liefern Beiträge):
\[
  \sum M_D = 0:\quad \tfrac{{S_4}}{{\sqrt{{2}}}}\cdot\tfrac{{L}}{{2}} - \tfrac{{P}}{{2}}\cdot L = 0
  \quad\Rightarrow\quad \boxed{{S_4 = \sqrt{{2}}\,P = {fd(S4, 2)}\,\text{{kN (Zug)}}}}
\]

\textbf{{$S_6$}} -- Momentensumme um E
([4] und [5] laufen durch E; nur $S_6$ und $B_V$ liefern Beiträge):
\[
  \sum M_E = 0:\quad -\tfrac{{L}}{{2}}\cdot\tfrac{{S_6}}{{\sqrt{{2}}}} - \tfrac{{P}}{{2}}\cdot\tfrac{{L}}{{2}} = 0
  \quad\Rightarrow\quad \boxed{{S_6 = -\tfrac{{P}}{{\sqrt{{2}}}} = {fd(S6, 2)}\,\text{{kN (Druck)}}}}
\]

\medskip
\begin{{center}}
\begin{{tabular}}{{ccccc}}
\toprule
$S_8$ & $S_9$ & $S_4$ & $S_5$ & $S_6$ \\
\midrule
$\tfrac{{P}}{{\sqrt{{2}}}} = {fd(S8,2)}$ & $-\tfrac{{P}}{{2}} = {fd(S9,2)}$ &
$\sqrt{{2}}\,P = {fd(S4,2)}$ & $-\tfrac{{P}}{{2}} = {fd(S5,2)}$ & $-\tfrac{{P}}{{\sqrt{{2}}}} = {fd(S6,2)}$ \\
\multicolumn{{5}}{{c}}{{\small [kN];\quad $+$ = Zug,\quad $-$ = Druck}} \\
\bottomrule
\end{{tabular}}
\end{{center}}
"""

    bsp2_sol = rf"""
\newpage
\section*{{2.~Beispiel \hfill (30\,\%)}}

\textbf{{Gegeben:}} Einfeldträger (Spannweite $L$) mit Dreieckslast
(0 bei A bis $q_0$ bei B),
$A_V = \tfrac{{1}}{{6}}q_0 L = {fd(AV2,2)}$\,kN,
$B_V = \tfrac{{1}}{{3}}q_0 L = {fd(BV2,2)}$\,kN, und
\[
  M(x) = -\tfrac{{q_0}}{{6L}}\,x^3 + \tfrac{{q_0 L}}{{6}}\,x.
\]

\textbf{{Systemwerte:}} $L = {lL}$\,m,\quad $q_0 = {lq0}$\,kN/m.

\subsection*{{2.1\quad Querkraft $V(x)$}}

Durch Ableitung des Momentenverlaufs:
\[
  V(x) = \frac{{\mathrm{{d}}M}}{{\mathrm{{d}}x}}
        = -\frac{{q_0}}{{2L}}\,x^2 + \frac{{q_0 L}}{{6}}
  \quad\Rightarrow\quad
  \boxed{{V(x) = \frac{{q_0 L}}{{6}} - \frac{{q_0}}{{2L}}\,x^2}}
\]
Kontrolle: $V(0) = \tfrac{{1}}{{6}}q_0 L = A_V$\,\checkmark;\quad
$V(L) = \tfrac{{1}}{{6}}q_0 L - \tfrac{{1}}{{2}}q_0 L = -\tfrac{{1}}{{3}}q_0 L = -B_V$\,\checkmark.

\subsection*{{2.2\quad Ort des maximalen Moments ($V = 0$)}}

\[
  \frac{{q_0 L}}{{6}} = \frac{{q_0}}{{2L}}\,x^2
  \;\Rightarrow\; x^2 = \frac{{L^2}}{{3}}
  \;\Rightarrow\; \boxed{{x_{{\max}} = \frac{{L}}{{\sqrt{{3}}}} \approx {fd(xmax2,4)}\,\text{{m}}}}
\]

\subsection*{{2.3\quad Maximales Moment}}

\[
  M_{{\max}} = M\!\left(\tfrac{{L}}{{\sqrt{{3}}}}\right)
  = -\frac{{q_0}}{{6L}}\cdot\frac{{L^3}}{{3\sqrt{{3}}}} + \frac{{q_0 L}}{{6}}\cdot\frac{{L}}{{\sqrt{{3}}}}
  = \frac{{q_0 L^2}}{{6}}\cdot\frac{{2}}{{3\sqrt{{3}}}}
  \;\Rightarrow\;
  \boxed{{M_{{\max}} = \frac{{q_0 L^2}}{{9\sqrt{{3}}}}
         = \frac{{\sqrt{{3}}}}{{27}}\,q_0 L^2 \approx {fd(Mmax2,4)}\,\text{{kNm}}}}
\]

\subsection*{{2.4\quad Verläufe}}

{tikz_bsp2_diagrams(p)}
"""

    doc  = preamble('de') + r"\begin{document}" + "\n"
    doc += header + sol + bsp2_sol
    doc += r"\end{document}" + "\n"
    return doc


# ══════════════════════════════════════════════════════════════════════════════
# 11. SOLUTION  –  ENGLISH
# ══════════════════════════════════════════════════════════════════════════════

def make_sol_en(p: dict, group: str, date_str: str, semester: str) -> str:
    L  = p['L']; q = p['q']; P = p['P']; q0 = p['q0']
    BV = p['BV']; AH = p['AH']; AV = p['AV']; MA = p['MA']
    S4 = p['S4']; S5 = p['S5']; S6 = p['S6']; S8 = p['S8']; S9 = p['S9']
    AV2 = p['AV2']; BV2 = p['BV2']; xmax2 = p['xmax2']; Mmax2 = p['Mmax2']

    lL  = fd(L,  1 if L != int(L) else 0)
    lq  = fd(q,  0)
    lP  = fd(P,  0)
    lq0 = fd(q0, 0)

    M1s = fd(p['M1'](0));  V1s = fd(p['V1'](0));  N1s = fd(p['N1'](0))
    M1e = fd(p['M1'](L));  V1e = fd(p['V1'](L));  N1e = fd(p['N1'](L))
    M2s = fd(p['M2'](0));  V2s = fd(p['V2'](0));  N2s = fd(0.0)
    M2e = fd(p['M2'](L));  V2e = fd(p['V2'](L));  N2e = fd(0.0)

    header = rf"""
\fancyhead[L]{{\small Model Solution\quad VU Mechanics -- LAWI 100515 (PI)\quad {semester}}}
\fancyhead[R]{{\small 2nd Exercise Exam ({date_str})\quad Group~{group}}}
\fancyfoot[C]{{\small Model Solution}}
\fancyfoot[R]{{\small Page~\thepage}}
"""

    sol = rf"""
\begin{{center}}
  {{\Large\bfseries Model Solution}}\\[4pt]
  {{\large VU Mechanics -- LAWI 100515 (PI)\quad {semester}}}\\[2pt]
  {{\normalsize 2nd Exercise Exam ({date_str}) -- Group~{group}}}\\[2pt]
  {{\normalsize \textbf{{System values:}} $L = {lL}$\,m,\quad $q = {lq}$\,kN/m,\quad $P = {lP}$\,kN}}
\end{{center}}

\section*{{1.~Task \hfill (70\,\%)}}

{TIKZ_SYSTEM_SKETCH}

\subsection*{{1.1\quad Static Determinacy}}

The structure consists of \textbf{{two rigid bodies}}: beam A--C--G
(members [1],[2]) and the truss (nodes C,D,E,F,B; members [3]--[9]).

\textit{{Overall system:}} 2 bodies $\Rightarrow$ $2 \times 3 = 6$ equilibrium conditions.
Unknowns: support A (fixed, clamped) $= 3$, support B (roller) $= 1$,
hinge C between beam and truss $= 2$. Total $= 6$.
\[
  n = \underbrace{{3}}_{{A}} + \underbrace{{1}}_{{B}} + \underbrace{{2}}_{{C}} - 2 \cdot 3
    = 6 - 6 = 0
  \quad\Rightarrow\quad \boxed{{n = 0:\text{{ statically determinate}}}}
\]

\subsection*{{1.2\quad Support Reactions (general form as functions of $q$, $P$, $L$)}}

\textbf{{Truss sub-system}}
(joint forces $C_x$, $C_y$ from beam on truss; $B_V$ at B; $P$ at D):
\begin{{align*}}
  \sum M_C = 0:\quad & P \cdot \tfrac{{L}}{{2}} + B_V \cdot L = 0
    &&\Rightarrow\quad \boxed{{B_V = -\tfrac{{P}}{{2}}}} \\
  \sum F_x = 0:\quad & C_x + P = 0
    &&\Rightarrow\quad C_x = -P \\
  \sum F_y = 0:\quad & C_y + B_V = 0
    &&\Rightarrow\quad C_y = +\tfrac{{P}}{{2}}
\end{{align*}}

\textbf{{Entire system}} (resultant distributed load $Q = 2qL$ at $x = L$):
\begin{{align*}}
  \sum F_x = 0:\quad & A_H + P = 0
    &&\Rightarrow\quad \boxed{{A_H = -P}} \\
  \sum F_y = 0:\quad & A_V + B_V - 2qL = 0
    &&\Rightarrow\quad \boxed{{A_V = 2qL + \tfrac{{P}}{{2}}}} \\
  \sum M_A = 0:\quad & M_A - 2qL \cdot L + P\cdot\tfrac{{L}}{{2}} + B_V \cdot 2L = 0
    &&\Rightarrow\quad \boxed{{M_A = 2qL^2 + \tfrac{{PL}}{{2}}}}
\end{{align*}}

\subsection*{{1.3\quad Numerical Values}}

\begin{{center}}
\begin{{tabular}}{{cccc}}
\toprule
$A_V$ & $A_H$ & $M_A$ & $B_V$ \\
\midrule
$2qL + \tfrac{{P}}{{2}} = \mathbf{{{fd(AV, 2)}}}$\,kN
& $-P = \mathbf{{{fd(AH, 2)}}}$\,kN
& $2qL^2 + \tfrac{{PL}}{{2}} = \mathbf{{{fd(MA, 2)}}}$\,kNm
& $-\tfrac{{P}}{{2}} = \mathbf{{{fd(BV, 2)}}}$\,kN \\
\bottomrule
\end{{tabular}}
\end{{center}}

Signs: positive $\uparrow$ for $A_V$, $B_V$; positive $\rightarrow$ for $A_H$;
CCW for $M_A$. Negative $\Rightarrow$ actual direction reversed.

\subsection*{{1.4\quad Section Forces in Beams [1] and [2]}}

At node C the truss applies force $(-C_x,\,-C_y) = (+P,\,-\tfrac{{P}}{{2}})$
to the beam (rightward $P$, downward $\tfrac{{P}}{{2}}$).
Running variable $x$ measured from the left end of each beam.

\textbf{{Beam~[1] (A\,$\to$\,C), $0 \le x \le L$:}}
\begin{{align*}}
  N_1(x) &= P \quad\text{{(constant, tension)}} \\
  V_1(x) &= \Bigl(2qL + \tfrac{{P}}{{2}}\Bigr) - qx \\
  M_1(x) &= \Bigl(2qL + \tfrac{{P}}{{2}}\Bigr)x - \tfrac{{q}}{{2}}x^2
            - \Bigl(2qL^2 + \tfrac{{PL}}{{2}}\Bigr)
\end{{align*}}

\textbf{{Beam~[2] (C\,$\to$\,G), $0 \le x \le L$:}}
\begin{{align*}}
  N_2(x) &= 0 \\
  V_2(x) &= q(L - x) \\
  M_2(x) &= -\tfrac{{q}}{{2}}(L - x)^2
\end{{align*}}

At C: shear jump $-\tfrac{{P}}{{2}}$ (vertical truss force);
normal-force jump $-P$ (horizontal truss force); moment continuous but with kink.

\medskip
\begin{{center}}
\begin{{tabular}}{{l cccccc}}
\toprule
 & \multicolumn{{3}}{{c}}{{\textbf{{Beam start}}}} & \multicolumn{{3}}{{c}}{{\textbf{{Beam end}}}} \\
\cmidrule(lr){{2-4}}\cmidrule(lr){{5-7}}
 & $M$\,[kNm] & $V$\,[kN] & $N$\,[kN]
 & $M$\,[kNm] & $V$\,[kN] & $N$\,[kN] \\
\midrule
Beam~[1] (A$\to$C) & ${M1s}$ & ${V1s}$ & ${N1s}$ & ${M1e}$ & ${V1e}$ & ${N1e}$ \\[3pt]
Beam~[2] (C$\to$G) & ${M2s}$ & ${V2s}$ & ${N2s}$ & ${M2e}$ & ${V2e}$ & ${N2e}$ \\
\bottomrule
\end{{tabular}}
\end{{center}}

\subsection*{{1.5\quad Distributions $M(x)$, $V(x)$, $N(x)$}}

{tikz_mvn_diagrams(p)}

\subsection*{{1.6\quad Axial Forces $S_8$ and $S_9$ -- Circular Cut at Node B}}

At B: member [8] (B$\to$E, direction $\tfrac{{1}}{{\sqrt{{2}}}}(-1,+1)$),
member [9] (B$\to$F, direction $(-1,\,0)$), support $B_V = -\tfrac{{P}}{{2}}$.
\begin{{align*}}
  \sum F_y = 0:\quad & \tfrac{{S_8}}{{\sqrt{{2}}}} + B_V = 0
    &&\Rightarrow\quad \boxed{{S_8 = \tfrac{{P}}{{\sqrt{{2}}}} \approx {fd(S8,2)}\,\text{{kN (tension)}}}} \\
  \sum F_x = 0:\quad & -\tfrac{{S_8}}{{\sqrt{{2}}}} - S_9 = 0
    &&\Rightarrow\quad \boxed{{S_9 = -\tfrac{{P}}{{2}} = {fd(S9,2)}\,\text{{kN (compression)}}}}
\end{{align*}}

\subsection*{{1.7\quad Axial Forces $S_4$, $S_5$, $S_6$ -- Ritter's Cut}}

Section through [4],[5],[6]; right part \{{E,F,B\}} ($B_V = -\tfrac{{P}}{{2}}$ external; $P$ in left part).
Members [4] (C--E) and [6] (D--F): $-45^\circ$; member [5] (D--E): horizontal.

\textbf{{$S_5$}} -- project all right-part forces onto $\tfrac{{1}}{{\sqrt{{2}}}}(1,1)$
(perpendicular to [4] and [6]):
\[
  -\tfrac{{S_5}}{{\sqrt{{2}}}} - \tfrac{{P}}{{2\sqrt{{2}}}} = 0
  \;\Rightarrow\; \boxed{{S_5 = -\tfrac{{P}}{{2}} = {fd(S5,2)}\,\text{{kN (compression)}}}}
\]

\textbf{{$S_4$}} -- moment sum about D ([5] and [6] pass through D):
\[
  \tfrac{{S_4}}{{\sqrt{{2}}}}\cdot\tfrac{{L}}{{2}} - \tfrac{{P}}{{2}}\cdot L = 0
  \;\Rightarrow\; \boxed{{S_4 = \sqrt{{2}}\,P = {fd(S4,2)}\,\text{{kN (tension)}}}}
\]

\textbf{{$S_6$}} -- moment sum about E ([4] and [5] pass through E):
\[
  -\tfrac{{L}}{{2}}\cdot\tfrac{{S_6}}{{\sqrt{{2}}}} - \tfrac{{P}}{{2}}\cdot\tfrac{{L}}{{2}} = 0
  \;\Rightarrow\; \boxed{{S_6 = -\tfrac{{P}}{{\sqrt{{2}}}} = {fd(S6,2)}\,\text{{kN (compression)}}}}
\]

\medskip
\begin{{center}}
\begin{{tabular}}{{ccccc}}
\toprule
$S_8$ & $S_9$ & $S_4$ & $S_5$ & $S_6$ \\
\midrule
$\tfrac{{P}}{{\sqrt{{2}}}} = {fd(S8,2)}$ & $-\tfrac{{P}}{{2}} = {fd(S9,2)}$ &
$\sqrt{{2}}\,P = {fd(S4,2)}$ & $-\tfrac{{P}}{{2}} = {fd(S5,2)}$ & $-\tfrac{{P}}{{\sqrt{{2}}}} = {fd(S6,2)}$ \\
\multicolumn{{5}}{{c}}{{\small [kN];\quad $+$ = tension,\quad $-$ = compression}} \\
\bottomrule
\end{{tabular}}
\end{{center}}
"""

    bsp2_sol = rf"""
\newpage
\section*{{2.~Task \hfill (30\,\%)}}

\textbf{{Given:}} Simply supported beam (span $L$) with triangular load
(0 at A, $q_0$ at B),
$A_V = \tfrac{{1}}{{6}}q_0 L = {fd(AV2,2)}$\,kN,
$B_V = \tfrac{{1}}{{3}}q_0 L = {fd(BV2,2)}$\,kN, and
\[
  M(x) = -\tfrac{{q_0}}{{6L}}\,x^3 + \tfrac{{q_0 L}}{{6}}\,x.
\]
\textbf{{Values:}} $L = {lL}$\,m,\quad $q_0 = {lq0}$\,kN/m.

\subsection*{{2.1\quad Shear Force $V(x)$}}

\[
  V(x) = \frac{{\mathrm{{d}}M}}{{\mathrm{{d}}x}}
        = \frac{{q_0 L}}{{6}} - \frac{{q_0}}{{2L}}\,x^2
\]
Check: $V(0) = \tfrac{{1}}{{6}}q_0 L = A_V$\;\checkmark;\quad
$V(L) = -\tfrac{{1}}{{3}}q_0 L = -B_V$\;\checkmark.

\subsection*{{2.2\quad Location of Maximum Moment ($V = 0$)}}

\[
  \frac{{q_0 L}}{{6}} = \frac{{q_0}}{{2L}}\,x^2
  \;\Rightarrow\; \boxed{{x_{{\max}} = \frac{{L}}{{\sqrt{{3}}}} \approx {fd(xmax2,4)}\,\text{{m}}}}
\]

\subsection*{{2.3\quad Maximum Moment}}

\[
  \boxed{{M_{{\max}} = \frac{{q_0 L^2}}{{9\sqrt{{3}}}}
       = \frac{{\sqrt{{3}}}}{{27}}\,q_0 L^2 \approx {fd(Mmax2,4)}\,\text{{kNm}}}}
\]

\subsection*{{2.4\quad Distributions}}

{tikz_bsp2_diagrams(p)}
"""

    doc  = preamble('en') + r"\begin{document}" + "\n"
    doc += header + sol + bsp2_sol
    doc += r"\end{document}" + "\n"
    return doc


# ══════════════════════════════════════════════════════════════════════════════
# 12. COMPILE & WRITE
# ══════════════════════════════════════════════════════════════════════════════

def write_and_compile(content: str, path: Path, compile_pdf: bool) -> bool:
    path.write_text(content, encoding='utf-8')
    if not compile_pdf:
        return True
    out_dir = path.parent
    cmd = [
        'pdflatex', '-interaction=nonstopmode',
        '-halt-on-error',
        f'-output-directory={out_dir}',
        str(path),
    ]
    # Run twice for correct page numbers / references
    ok = True
    for _ in range(2):
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=out_dir)
        if result.returncode != 0:
            print(f"  [LaTeX ERROR] {path.name}")
            log = out_dir / path.stem
            log = log.with_suffix('.log')
            if log.exists():
                lines = log.read_text(errors='replace').splitlines()
                errs = [l for l in lines if l.startswith('!') or 'Error' in l]
                for e in errs[:10]:
                    print(f"    {e}")
            ok = False
            break
    # Clean auxiliary files
    for ext in ('.aux', '.log', '.out', '.fls', '.fdb_latexmk'):
        aux = path.with_suffix(ext)
        if aux.exists():
            aux.unlink()
    return ok


# ══════════════════════════════════════════════════════════════════════════════
# 13. MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Generate random 2nd Exercise Exam for VU Mechanik LAWI 100515')
    parser.add_argument('--seed',       type=int,   default=None,
                        help='RNG seed (default: random)')
    parser.add_argument('--group',      default=None,
                        choices=['A', 'B', 'C', 'D'],
                        help='Exam group (default: random)')
    parser.add_argument('--date',       default=None,
                        help='Exam date YYYY-MM-DD (default: today)')
    parser.add_argument('--semester',   default=None,
                        help='Semester label, e.g. "SS 2026" (default: auto)')
    parser.add_argument('--out',        default=None,
                        help='Output directory (default: exam_generator/output)')
    parser.add_argument('--no-compile', action='store_true',
                        help='Generate .tex files only, skip PDF compilation')
    args = parser.parse_args()

    # ── Resolve defaults ─────────────────────────────────────────────────────
    seed   = args.seed   if args.seed   is not None else random.randint(0, 9999)
    group  = args.group  if args.group  is not None else random.choice(['A', 'B', 'C', 'D'])
    today  = _today.today()
    date_str = args.date if args.date else today.strftime('%d.%m.%Y')
    if args.semester:
        semester = args.semester
    else:
        semester = f"SS {today.year}" if today.month >= 3 and today.month <= 9 else \
                   f"WS {today.year}/{str(today.year+1)[2:]}"

    script_dir = Path(__file__).parent
    out_dir    = Path(args.out) if args.out else script_dir / 'output'
    out_dir.mkdir(parents=True, exist_ok=True)

    compile_pdf = not args.no_compile

    print(f"\n{'='*60}")
    print(f"  VU Mechanik – Exam Generator")
    print(f"  Seed: {seed}  |  Group: {group}  |  Date: {date_str}")
    print(f"  Semester: {semester}")
    print(f"  Output: {out_dir}")
    print(f"{'='*60}")

    # ── Build solution ───────────────────────────────────────────────────────
    p = build_solution(seed)
    print(f"\n  Parameters: L={p['L']}m, q={p['q']}kN/m, P={p['P']}kN, q0={p['q0']}kN/m")
    print(f"  Reactions:  AV={fd(p['AV'],2)}kN, AH={fd(p['AH'],2)}kN, "
          f"MA={fd(p['MA'],2)}kNm, BV={fd(p['BV'],2)}kN")
    print(f"  Truss:      S4={fd(p['S4'],2)}, S5={fd(p['S5'],2)}, "
          f"S6={fd(p['S6'],2)}, S8={fd(p['S8'],2)}, S9={fd(p['S9'],2)} [kN]")

    # ── File stem ────────────────────────────────────────────────────────────
    stem = f"seed{seed:04d}_Gruppe{group}"

    files = [
        (f"Klausur_{stem}_DE.tex",  make_exam_de( p, group, date_str, semester), 'DE Exam'),
        (f"Klausur_{stem}_EN.tex",  make_exam_en( p, group, date_str, semester), 'EN Exam'),
        (f"ML_{stem}_DE.tex",       make_sol_de(  p, group, date_str, semester), 'DE Solution'),
        (f"ML_{stem}_EN.tex",       make_sol_en(  p, group, date_str, semester), 'EN Solution'),
    ]

    print()
    for fname, content, label in files:
        path = out_dir / fname
        ok   = write_and_compile(content, path, compile_pdf)
        pdf  = path.with_suffix('.pdf')
        status = 'OK  →  ' + str(pdf) if (ok and pdf.exists()) else 'TEX written (no PDF)'
        print(f"  [{label:14s}]  {status}")

    print(f"\n  Seed {seed} – use --seed {seed} to reproduce this exam.\n")


if __name__ == '__main__':
    main()
