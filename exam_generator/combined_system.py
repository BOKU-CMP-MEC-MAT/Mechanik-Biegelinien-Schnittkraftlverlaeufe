#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
combined_system.py
==================================================================
Data-driven model + exact solver for the combined exam system used
in VU Mechanik (LAWI 100515):

    Two Scheiben joined by a SINGLE hinge:
       Scheibe 1 :  bending beam  (fixed support at A, hinge at C)
       Scheibe 2 :  pin-jointed truss (roller support at B)

The whole structure is statically determinate:
       r_ext = 4   (fixed = 3  +  roller = 1)
       2 rigid bodies * 3 equilibrium eq. = 6 = 4 + 2 (hinge force)

Everything (geometry, supports, loads) is generated randomly inside
this family and SOLVED FROM THE DATA — no hard-coded formulas — so the
result stays correct for whatever system is rolled.

Sign conventions
----------------
  * x to the right, y upwards.
  * Bar axial force  N>0  =>  tension.
  * Beam section forces, left part of a cut at x:
        N(x) = -sum(horizontal ext. forces left)        (tension +)
        V(x) =  sum(vertical   ext. forces left, up +)
        M(x) =  sum of moments of left ext. forces about the cut
                (sagging positive)
"""

from __future__ import annotations
import math
import random
from fractions import Fraction as Fr
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np


# ════════════════════════════════════════════════════════════════════
#  DATA MODEL
# ════════════════════════════════════════════════════════════════════
@dataclass
class System:
    """A complete combined beam+truss system."""
    # geometry --------------------------------------------------------
    joints: Dict[str, Tuple[float, float]]          # name -> (x, y)
    bars:   List[Tuple[str, str]]                   # truss members (i, j)
    beam_nodes: List[str]                           # ordered nodes of the beam Scheibe
    # connectivity ----------------------------------------------------
    hinge: str                                      # joint shared by beam & truss
    # supports --------------------------------------------------------
    fixed: str                                      # fixed support node (on beam)
    roller: str                                     # roller support node (on truss)
    # loads -----------------------------------------------------------
    q: float = 0.0                                  # UDL intensity on beam [kN/m] (downward)
    q_a: float = 0.0                                # UDL start x
    q_b: float = 0.0                                # UDL end   x
    point_loads: List[Tuple[str, float, float]] = field(default_factory=list)
    #                       (joint, Fx, Fy)  downward => Fy<0
    # bookkeeping -----------------------------------------------------
    n_panels: int = 2
    panel: float = 2.0
    height: float = 2.0
    beam_len: float = 4.0
    seed: int = 0

    # convenience -----------------------------------------------------
    def x(self, n): return self.joints[n][0]
    def y(self, n): return self.joints[n][1]


# ════════════════════════════════════════════════════════════════════
#  SYSTEM GENERATION  (parametric, within the example's family)
# ════════════════════════════════════════════════════════════════════
def build_system(seed: int) -> System:
    rng = random.Random(seed)

    # --- random geometry --------------------------------------------
    n      = rng.choice([2, 3])               # number of truss panels
    panel  = float(rng.choice([1.5, 2.0]))    # panel length
    height = panel                            # 45° diagonals  -> clean sqrt2 forces
    a      = float(rng.choice([3.0, 4.0, 5.0]))   # beam length A->C

    # --- nodes -------------------------------------------------------
    joints: Dict[str, Tuple[float, float]] = {}
    joints['A'] = (0.0, 0.0)
    joints['C'] = (a, 0.0)                    # hinge node (top-left of truss)

    # truss: parallel-chord (Pratt) truss to the right of C
    top = ['C']
    for k in range(1, n + 1):
        name = f'O{k}'
        joints[name] = (a + k * panel, 0.0)
        top.append(name)
    bot = []
    for k in range(0, n + 1):
        name = f'U{k}'
        joints[name] = (a + k * panel, -height)
        bot.append(name)

    bars: List[Tuple[str, str]] = []
    # top chord
    for k in range(n):
        bars.append((top[k], top[k + 1]))
    # bottom chord
    for k in range(n):
        bars.append((bot[k], bot[k + 1]))
    # verticals
    for k in range(n + 1):
        bars.append((top[k], bot[k]))
    # diagonals (Pratt: bottom-left -> top-right)
    for k in range(n):
        bars.append((bot[k], top[k + 1]))

    # --- supports ----------------------------------------------------
    fixed  = 'A'
    roller = bot[-1]            # roller at far bottom-right node

    # --- loads -------------------------------------------------------
    # The truss is only engaged when a load sits on the TRUSS Scheibe,
    # so we ALWAYS apply a point load at an interior bottom truss node
    # (never the roller node, never the node directly under the hinge).
    q = q_a = q_b = 0.0
    point_loads: List[Tuple[str, float, float]] = []

    interior = bot[1:-1] if n >= 2 else [bot[0]]     # U1 .. U_{n-1}
    if not interior:                                 # n == 1 fallback
        interior = [bot[0]]
    node = rng.choice(interior)
    P    = float(rng.choice([10, 12, 15, 20]))
    Hx   = 0.0
    if rng.random() < 0.35:                          # sometimes inclined -> N != 0
        Hx = float(rng.choice([5, 8, 10]))
    point_loads.append((node, Hx, -P))               # (Fx, Fy)

    # optionally an additional UDL on the beam (downward)
    if rng.random() < 0.6:
        q   = float(rng.choice([2, 3, 4, 5, 6]))
        q_a = 0.0
        q_b = a                                       # full-span UDL on the beam

    return System(joints=joints, bars=bars, beam_nodes=['A', 'C'],
                  hinge='C', fixed=fixed, roller=roller,
                  q=q, q_a=q_a, q_b=q_b, point_loads=point_loads,
                  n_panels=n, panel=panel, height=height, beam_len=a, seed=seed)


# ════════════════════════════════════════════════════════════════════
#  EXACT GLOBAL SOLVE  (Scheibe method, Fractions)
# ════════════════════════════════════════════════════════════════════
def _frac(x) -> Fr:
    return Fr(x).limit_denominator(10**6)


def solve_global(sys: System) -> dict:
    """
    Unknowns: Ax, Ay, MA  (fixed at A)   Cx, Cy (hinge force on BEAM)   By (roller).
    6 equations: 3 for beam Scheibe, 3 for truss Scheibe.
    Returns exact Fractions.
    """
    a = _frac(sys.beam_len)
    # --- applied loads on beam (UDL) ---------------------------------
    qf  = _frac(sys.q)
    qa  = _frac(sys.q_a)
    qb  = _frac(sys.q_b)
    Lq  = qb - qa
    Wq  = qf * Lq                      # total UDL magnitude (downward)
    xq  = (qa + qb) / 2                # centroid

    # --- truss applied point loads -----------------------------------
    # split into those on the truss (everything except possibly on beam)
    Pt = []   # (x, y, Fx, Fy)
    for (node, Fx, Fy) in sys.point_loads:
        px, py = sys.joints[node]
        Pt.append((_frac(px), _frac(py), _frac(Fx), _frac(Fy)))

    xC = a
    xB = _frac(sys.joints[sys.roller][0])

    # Unknown order: [Ax, Ay, MA, Cx, Cy, By]
    A = [[Fr(0)] * 6 for _ in range(6)]
    b = [Fr(0)] * 6

    # ---- Scheibe 1 : BEAM  (forces: A-reactions, hinge C on beam, UDL)
    # eq0  ΣFx = 0 :  Ax + Cx = 0
    A[0][0] = Fr(1); A[0][3] = Fr(1)
    b[0] = Fr(0)
    # eq1  ΣFy = 0 :  Ay + Cy - Wq = 0
    A[1][1] = Fr(1); A[1][4] = Fr(1)
    b[1] = Wq
    # eq2  ΣM_A = 0 (CCW+): MA + Cy*a - Wq*xq = 0
    A[2][2] = Fr(1); A[2][4] = a
    b[2] = Wq * xq

    # ---- Scheibe 2 : TRUSS (forces: -hinge at C, roller By, point loads)
    sumPx = sum(p[2] for p in Pt)
    sumPy = sum(p[3] for p in Pt)
    # eq3  ΣFx = 0 :  -Cx + sumPx = 0
    A[3][3] = Fr(-1)
    b[3] = -sumPx
    # eq4  ΣFy = 0 :  -Cy + By + sumPy = 0
    A[4][4] = Fr(-1); A[4][5] = Fr(1)
    b[4] = -sumPy
    # eq5  ΣM_C = 0 (CCW+):  By*(xB - xC) + Σ Pi moment about C = 0
    #   moment of (Fx,Fy) at (px,py) about C=(xC,0): (px-xC)*Fy - (py-0)*Fx
    A[5][5] = (xB - xC)
    mom = Fr(0)
    for (px, py, Fx, Fy) in Pt:
        mom += (px - xC) * Fy - (py) * Fx
    b[5] = -mom

    sol = _solve_fraction(A, b)
    Ax, Ay, MA, Cx, Cy, By = sol
    return dict(Ax=Ax, Ay=Ay, MA=MA, Cx=Cx, Cy=Cy, By=By)


def _solve_fraction(A: List[List[Fr]], b: List[Fr]) -> List[Fr]:
    """Exact Gaussian elimination with partial pivoting over Fractions."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = None
        for r in range(col, n):
            if M[r][col] != 0:
                piv = r
                break
        if piv is None:
            raise ValueError("singular system (mechanism / unstable geometry)")
        M[col], M[piv] = M[piv], M[col]
        pivval = M[col][col]
        M[col] = [v / pivval for v in M[col]]
        for r in range(n):
            if r != col and M[r][col] != 0:
                factor = M[r][col]
                M[r] = [a_ - factor * b_ for a_, b_ in zip(M[r], M[col])]
    return [M[i][n] for i in range(n)]


# ════════════════════════════════════════════════════════════════════
#  TRUSS MEMBER FORCES  (method of joints, exact-ish via linear solve)
# ════════════════════════════════════════════════════════════════════
def solve_truss(sys: System, glob: dict) -> Dict[Tuple[str, str], float]:
    """Solve the isolated truss for bar axial forces (tension +)."""
    truss_joints = sorted({j for bar in sys.bars for j in bar})
    jidx = {name: k for k, name in enumerate(truss_joints)}
    nj = len(truss_joints)
    nb = len(sys.bars)

    A = np.zeros((2 * nj, nb))
    rhs = np.zeros(2 * nj)

    for b, (i, j) in enumerate(sys.bars):
        xi, yi = sys.joints[i]
        xj, yj = sys.joints[j]
        dx, dy = xj - xi, yj - yi
        L = math.hypot(dx, dy)
        ux, uy = dx / L, dy / L
        # tension pulls joint i toward j  => (+ux,+uy) at i ;  (-ux,-uy) at j
        A[2 * jidx[i],     b] += ux
        A[2 * jidx[i] + 1, b] += uy
        A[2 * jidx[j],     b] += -ux
        A[2 * jidx[j] + 1, b] += -uy

    # external forces on the truss:
    #   hinge reaction at C  =  -(Cx, Cy)   (reaction to force on beam)
    Cx = float(glob['Cx']); Cy = float(glob['Cy'])
    rhs[2 * jidx[sys.hinge]]     -= -Cx
    rhs[2 * jidx[sys.hinge] + 1] -= -Cy
    #   roller reaction at B  =  (0, By)
    By = float(glob['By'])
    rhs[2 * jidx[sys.roller] + 1] -= By
    #   applied point loads
    for (node, Fx, Fy) in sys.point_loads:
        rhs[2 * jidx[node]]     -= Fx
        rhs[2 * jidx[node] + 1] -= Fy

    # solve (overdetermined by 3 but consistent) via least squares
    f, res, rank, sv = np.linalg.lstsq(A, rhs, rcond=None)
    residual = float(np.max(np.abs(A @ f - rhs)))
    if rank < nb or residual > 1e-6:
        raise ValueError(f"truss not solvable (rank {rank}/{nb}, res {residual:.2e})")

    forces = {}
    for b, bar in enumerate(sys.bars):
        val = f[b]
        if abs(val) < 1e-9:
            val = 0.0
        forces[bar] = val
    return forces


# ════════════════════════════════════════════════════════════════════
#  BEAM SECTION FORCES  N(x), V(x), M(x)   along A -> C
# ════════════════════════════════════════════════════════════════════
def beam_section_forces(sys: System, glob: dict):
    """
    Return python callables N,V,M valid for x in [0, beam_len].

    Evaluated from the RIGHT part of the cut (everything from x to the
    hinge C).  The only external actions on that part are the hinge
    force (Cx,Cy) at C and the portion of the UDL on [x, q_b]:

        N(x) =  sum_right Fx                       (tension +)
        V(x) = -sum_right Fy
        M(x) =  sum_right Fy*(x - x_i)             (sagging +)
    """
    a  = sys.beam_len
    Cx = float(glob['Cx']); Cy = float(glob['Cy'])
    q  = sys.q; qa = sys.q_a; qb = sys.q_b

    def _udl_right(x):
        x0 = max(x, qa)
        return (x0, qb) if qb > x0 else None

    def N(x):
        return Cx                      # horizontal hinge force (no horiz load on beam)

    def V(x):
        s = Cy                         # hinge vertical
        seg = _udl_right(x)
        if seg:
            x0, x1 = seg
            s += -q * (x1 - x0)        # remaining UDL (downward)
        return -s

    def M(x):
        m = Cy * (x - a)               # hinge force at C
        seg = _udl_right(x)
        if seg:
            x0, x1 = seg
            # integral of (-q)*(x - t) dt  over [x0, x1]
            m += -q * (x * (x1 - x0) - 0.5 * (x1 * x1 - x0 * x0))
        return m

    return N, V, M


# ════════════════════════════════════════════════════════════════════
#  FULL SOLVE + EQUILIBRIUM SELF-CHECK
# ════════════════════════════════════════════════════════════════════
def solve(sys: System) -> dict:
    glob = solve_global(sys)
    truss = solve_truss(sys, glob)
    N, V, M = beam_section_forces(sys, glob)
    _check_equilibrium(sys, glob)
    return dict(glob=glob, truss=truss, N=N, V=V, M=M)


def _check_equilibrium(sys: System, glob: dict, tol=1e-9):
    """Verify global equilibrium of the WHOLE structure."""
    Ax = float(glob['Ax']); Ay = float(glob['Ay']); MA = float(glob['MA'])
    By = float(glob['By'])
    # all external forces: A reaction, B reaction, UDL, point loads
    Fx = Ax
    Fy = Ay + By
    Mo = MA + Ay * 0 + Ax * 0          # moment about origin A
    Mo += By * sys.joints[sys.roller][0]    # roller vertical at xB
    # UDL
    Wq = sys.q * max(0.0, sys.q_b - sys.q_a)
    xq = (sys.q_a + sys.q_b) / 2
    Fy += -Wq
    Mo += -Wq * xq
    # point loads
    for (node, fx, fy) in sys.point_loads:
        px, py = sys.joints[node]
        Fx += fx
        Fy += fy
        Mo += px * fy - py * fx
    assert abs(Fx) < tol, f"ΣFx={Fx}"
    assert abs(Fy) < tol, f"ΣFy={Fy}"
    assert abs(Mo) < tol, f"ΣM={Mo}"


# ════════════════════════════════════════════════════════════════════
#  SELF-TEST
# ════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    for seed in range(12):
        try:
            sys = build_system(seed)
            res = solve(sys)
            g = res['glob']
            print(f"seed {seed:2d}  n={sys.n_panels} a={sys.beam_len} p={sys.panel} "
                  f"load: q={sys.q} pts={sys.point_loads}")
            print(f"    A_x={float(g['Ax']):+.2f} A_y={float(g['Ay']):+.2f} "
                  f"M_A={float(g['MA']):+.2f} | C=({float(g['Cx']):+.2f},{float(g['Cy']):+.2f}) "
                  f"B_y={float(g['By']):+.2f}")
            # truss extremes
            fmax = max(res['truss'].values())
            fmin = min(res['truss'].values())
            print(f"    truss bars: {len(sys.bars)}  S_max={fmax:+.2f}  S_min={fmin:+.2f}")
            # beam section checks:  M(0) must equal M_A, M(a) must equal 0
            N, V, M = res['N'], res['V'], res['M']
            a = sys.beam_len
            assert abs(M(0) - float(g['MA'])) < 1e-6, f"M(0)={M(0)} != MA"
            assert abs(M(a)) < 1e-6, f"M(a)={M(a)} != 0"
            assert abs(V(0) - float(g['Ay'])) < 1e-6, f"V(0) != Ay"
            print(f"    beam:  M(0)={M(0):+.2f}(=MA)  M(a)={M(a):+.2f}(=0)  "
                  f"V(0)={V(0):+.2f}  N={N(0):+.2f}   [checks OK]")
        except Exception as e:
            print(f"seed {seed:2d}  FAILED: {e}")
