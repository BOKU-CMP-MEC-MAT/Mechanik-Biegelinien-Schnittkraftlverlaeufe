#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_combined_exam.py
==================================================================
Random EXAM generator for VU Mechanik (LAWI 100515) — combined
beam + truss systems (two Scheiben joined by a single hinge), in the
style of the original course exams.

For every seed it
  * builds a random, statically determinate combined system,
  * solves it exactly (combined_system.py),
  * renders the system + M/V/N diagrams + truss forces in TikZ,
  * writes German & English exam sheets and full solutions,
  * compiles all four to PDF.

Usage:
    python generate_combined_exam.py --seed 42 --group A \
        --date 26.06.2026 --semester "SS 2026"
"""

from __future__ import annotations
import argparse
import math
import subprocess
from pathlib import Path

import combined_system as cs


# ════════════════════════════════════════════════════════════════════
#  NUMBER FORMATTING
# ════════════════════════════════════════════════════════════════════
def fnum(v: float, lang: str = 'de', dec: int = 2) -> str:
    """Round and format a number; German uses a decimal comma."""
    if abs(v) < 5e-3:
        v = 0.0
    s = f"{v:.{dec}f}".rstrip('0').rstrip('.')
    if s in ('', '-0'):
        s = '0'
    if lang == 'de':
        s = s.replace('.', ',')
    return s


def fsigned(v: float, lang: str = 'de', dec: int = 2) -> str:
    s = fnum(abs(v), lang, dec)
    return ('-' if v < -5e-3 else '+') + s


# ════════════════════════════════════════════════════════════════════
#  TIKZ HELPERS
# ════════════════════════════════════════════════════════════════════
def C(x: float, y: float) -> str:
    return f"({x:.3f},{y:.3f})"


def member_labels(sys: cs.System):
    """Map every bar to a number [1..m]; beam members get B-labels."""
    return {bar: i + 1 for i, bar in enumerate(sys.bars)}


# ---- system sketch (the Angabe drawing) ----------------------------
def tikz_system(sys: cs.System, show_numbers: bool = True) -> str:
    J = sys.joints
    a = sys.beam_len
    H = sys.height
    lab = member_labels(sys)
    L: list[str] = []
    L.append(r"\begin{center}")
    L.append(rf"\begin{{tikzpicture}}[scale=1.15, rotate={sys.theta}, "
             r">=Stealth, line join=round]")

    # coordinates
    for name, (x, y) in J.items():
        L.append(rf"  \coordinate ({name}) at {C(x, y)};")

    # --- truss bars ---
    for bar in sys.bars:
        i, j = bar
        L.append(rf"  \draw[thick] ({i}) -- ({j});")
    # --- beam member A--C (drawn heavier) ---
    L.append(r"  \draw[line width=2.2pt] (A) -- (C);")

    # --- truss joints ---
    for name, (x, y) in J.items():
        if name in ('A',):
            continue
        L.append(rf"  \fill ({name}) circle (1.6pt);")
    # --- hinge at C (open circle) ---
    L.append(rf"  \draw[fill=white,line width=1pt] (C) circle (3.2pt);")

    # --- fixed support at A (wall on the left) ---
    ax, ay = J['A']
    L.append(rf"  \draw[line width=1.1pt] ({ax:.3f},{ay-0.55:.3f}) -- ({ax:.3f},{ay+0.55:.3f});")
    L.append(rf"  \fill[pattern=north east lines] ({ax-0.22:.3f},{ay-0.55:.3f}) "
             rf"rectangle ({ax:.3f},{ay+0.55:.3f});")
    L.append(rf"  \draw[line width=1.1pt] ({ax-0.22:.3f},{ay-0.55:.3f}) -- "
             rf"({ax-0.22:.3f},{ay+0.55:.3f});")

    # --- roller support at B (below the node) ---
    bx, by = J[sys.roller]
    L.append(rf"  \draw[thick] ({bx:.3f},{by:.3f}) -- ({bx-0.22:.3f},{by-0.34:.3f}) -- "
             rf"({bx+0.22:.3f},{by-0.34:.3f}) -- cycle;")
    L.append(rf"  \draw[thick] ({bx-0.16:.3f},{by-0.46:.3f}) circle (0.06) "
             rf"({bx+0.16:.3f},{by-0.46:.3f}) circle (0.06);")
    L.append(rf"  \draw[line width=1.1pt] ({bx-0.30:.3f},{by-0.54:.3f}) -- ({bx+0.30:.3f},{by-0.54:.3f});")
    L.append(rf"  \fill[pattern=north east lines] ({bx-0.30:.3f},{by-0.70:.3f}) "
             rf"rectangle ({bx+0.30:.3f},{by-0.54:.3f});")

    # --- UDL on the beam ---
    if sys.q > 0:
        top = 0.55
        L.append(rf"  \draw[blue!70!black,thick] ({sys.q_a:.3f},{top:.3f}) -- ({sys.q_b:.3f},{top:.3f});")
        nq = max(4, int(round((sys.q_b - sys.q_a) / max(sys.panel, 0.5))) + 4)
        for k in range(nq + 1):
            xx = sys.q_a + (sys.q_b - sys.q_a) * k / nq
            L.append(rf"  \draw[->,blue!70!black] ({xx:.3f},{top:.3f}) -- ({xx:.3f},0.06);")
        L.append(rf"  \node[blue!70!black,above] at ({(sys.q_a+sys.q_b)/2:.3f},{top:.3f}) {{$q$}};")

    # --- point loads (drawn as separate vertical P and horizontal H arrows) ---
    for (node, Fx, Fy) in sys.point_loads:
        nx, ny = J[node]
        if abs(Fy) > 1e-9:                         # vertical component (downward)
            L.append(rf"  \draw[->,red!80!black,line width=1.1pt] "
                     rf"({nx:.3f},{ny+0.95:.3f}) -- ({nx:.3f},{ny:.3f});")
            L.append(rf"  \node[red!80!black,above right] at ({nx:.3f},{ny+0.55:.3f}) {{$P$}};")
        if abs(Fx) > 1e-9:                         # horizontal component
            sgn = 1.0 if Fx > 0 else -1.0
            L.append(rf"  \draw[->,red!80!black,line width=1.1pt] "
                     rf"({nx-sgn*0.95:.3f},{ny:.3f}) -- ({nx:.3f},{ny:.3f});")
            L.append(rf"  \node[red!80!black,below] at ({nx-sgn*0.55:.3f},{ny:.3f}) {{$H$}};")

    # --- member numbers ---
    if show_numbers:
        for bar, num in lab.items():
            i, j = bar
            mx = (J[i][0] + J[j][0]) / 2
            my = (J[i][1] + J[j][1]) / 2
            L.append(rf"  \node[circle,fill=white,draw=gray!60,inner sep=0.7pt,"
                     rf"font=\scriptsize] at ({mx:.3f},{my:.3f}) {{\textbf{{{num}}}}};")

    # --- node labels ---
    L.append(rf"  \node[above left=1pt] at (A) {{$A$}};")
    L.append(rf"  \node[above=4pt] at (C) {{$C$}};")
    for name in J:
        if name in ('A', 'C'):
            continue
        if name == sys.roller:
            L.append(rf"  \node[above right=2pt] at ({name}) {{$B$}};")
        elif name.startswith('O'):
            L.append(rf"  \node[above=2pt] at ({name}) {{${name[0]}_{{{name[1:]}}}$}};")
        elif name.startswith('U'):
            L.append(rf"  \node[below=2pt] at ({name}) {{${name[0]}_{{{name[1:]}}}$}};")

    # --- dimension lines ---
    dy = -H - 0.95
    L.append(rf"  \draw[<->,gray] ({0:.3f},{dy:.3f}) -- ({a:.3f},{dy:.3f}) "
             rf"node[midway,below,font=\footnotesize]{{$a={fnum(a)}$\,m}};")
    L.append(rf"  \draw[<->,gray] ({a:.3f},{dy:.3f}) -- ({a+sys.panel:.3f},{dy:.3f}) "
             rf"node[midway,below,font=\footnotesize]{{$\ell={fnum(sys.panel)}$\,m}};")
    # height dimension placed just LEFT of C (clear of the truss & roller)
    L.append(rf"  \draw[<->,gray] ({a-0.45:.3f},0) -- ({a-0.45:.3f},{-H:.3f}) "
             rf"node[midway,left,font=\footnotesize]{{$h={fnum(H)}$\,m}};")

    L.append(r"\end{tikzpicture}")
    L.append(r"\end{center}")
    return "\n".join(L)


# ---- truss force result sketch (solution) --------------------------
def tikz_truss_solution(sys: cs.System, forces, lang: str) -> str:
    J = sys.joints
    L: list[str] = []
    L.append(r"\begin{center}")
    L.append(rf"\begin{{tikzpicture}}[scale=1.15, rotate={sys.theta}, "
             r">=Stealth, line join=round]")
    for name, (x, y) in J.items():
        L.append(rf"  \coordinate ({name}) at {C(x, y)};")
    for bar in sys.bars:
        i, j = bar
        f = forces[bar]
        col = 'red!75!black' if f > 1e-6 else ('blue!70!black' if f < -1e-6 else 'gray')
        L.append(rf"  \draw[thick,{col}] ({i}) -- ({j});")
    L.append(r"  \draw[line width=2.2pt] (A) -- (C);")
    for name in J:
        if name != 'A':
            L.append(rf"  \fill ({name}) circle (1.6pt);")
    # member numbers (values are listed in the table) on a white badge
    lab = member_labels(sys)
    for bar, num in lab.items():
        i, j = bar
        mx = (J[i][0] + J[j][0]) / 2
        my = (J[i][1] + J[j][1]) / 2
        L.append(rf"  \node[circle,fill=white,draw=gray!50,inner sep=0.6pt,"
                 rf"font=\scriptsize] at ({mx:.3f},{my:.3f}) {{{num}}};")
    L.append(rf"  \node[above left=1pt] at (A) {{$A$}};")
    L.append(rf"  \node[above=4pt] at (C) {{$C$}};")
    L.append(rf"  \node[below right=2pt] at ({sys.roller}) {{$B$}};")
    legend = "rot: Zug $(+)$ \\quad blau: Druck $(-)$" if lang == 'de' \
             else "red: tension $(+)$ \\quad blue: compression $(-)$"
    L.append(rf"  \node[font=\footnotesize,align=center] at "
             rf"({sys.beam_len/2:.2f},{sys.height+0.8:.2f}) {{{legend}}};")
    L.append(r"\end{tikzpicture}")
    L.append(r"\end{center}")
    return "\n".join(L)


# ---- one M/V/N diagram for the beam --------------------------------
def tikz_diagram(func, a: float, color: str, title: str, lang: str,
                 npts: int = 60) -> str:
    xs = [a * k / npts for k in range(npts + 1)]
    ys = [func(x) for x in xs]
    ymax = max((abs(y) for y in ys), default=1.0)
    if ymax < 1e-9:
        # identically zero
        L = [r"\begin{tikzpicture}[>=Stealth]",
             rf"  \draw[->] (-0.2,0) -- ({8.4:.2f},0) node[right]{{$x$}};",
             rf"  \draw[{color},very thick] (0,0) -- (8,0);",
             rf"  \node[{color}] at (4,0.35) {{{title}\,$\equiv 0$}};",
             r"\end{tikzpicture}"]
        return "\n".join(L)
    W, Hh = 8.0, 1.25
    sx = W / a
    sy = Hh / ymax
    coords = " ".join(f"({x*sx:.3f},{y*sy:.3f})" for x, y in zip(xs, ys))
    # extrema
    imax = max(range(len(ys)), key=lambda k: ys[k])
    imin = min(range(len(ys)), key=lambda k: ys[k])
    L = [r"\begin{tikzpicture}[>=Stealth]"]
    L.append(rf"  \draw[->] (-0.2,0) -- ({W+0.35:.2f},0) node[below right]{{$x$}};")
    L.append(rf"  \node[below=2pt] at (0,0) {{$A$}};")
    L.append(rf"  \node[below=2pt] at ({W:.2f},0) {{$C$}};")
    L.append(rf"  \filldraw[fill={color}!12,draw={color},thick] "
             rf"(0,0) -- plot coordinates {{{coords}}} -- ({W:.3f},0) -- cycle;")
    shown = set()
    for idx, anch in ((imax, 'above'), (imin, 'below')):
        if abs(ys[idx]) > 1e-3 * ymax + 1e-6 and idx not in shown:
            shown.add(idx)
            L.append(rf"  \node[{anch},{color},font=\footnotesize] "
                     rf"at ({xs[idx]*sx:.3f},{ys[idx]*sy:.3f}) {{{fnum(ys[idx], lang, 1)}}};")
    L.append(rf"  \node[{color},right] at ({W+0.8:.2f},0.35) {{{title}}};")
    L.append(r"\end{tikzpicture}")
    return "\n".join(L)


def truss_table(sys: cs.System, forces, lang: str) -> str:
    lab = member_labels(sys)
    head_n = "Stab" if lang == 'de' else "Member"
    head_f = "Stabkraft $S$ [kN]" if lang == 'de' else "Member force $S$ [kN]"
    head_t = "Art" if lang == 'de' else "Type"
    zug, druck, null = ("Zug", "Druck", "Nullstab") if lang == 'de' \
        else ("tension", "compression", "zero-force")
    rows = []
    for bar, num in lab.items():
        i, j = bar
        f = forces[bar]
        typ = zug if f > 1e-6 else (druck if f < -1e-6 else null)
        rows.append(rf"  {num} ({i}\,--\,{j}) & {fnum(f, lang, 2)} & {typ} \\")
    body = "\n".join(rows)
    return (r"\begin{center}\renewcommand{\arraystretch}{1.15}" "\n"
            r"\begin{tabular}{c r l}" "\n"
            r"\toprule" "\n"
            rf"{head_n} & {head_f} & {head_t} \\" "\n"
            r"\midrule" "\n"
            f"{body}\n"
            r"\bottomrule" "\n"
            r"\end{tabular}\end{center}")


# ════════════════════════════════════════════════════════════════════
#  LATEX DOCUMENT PIECES
# ════════════════════════════════════════════════════════════════════
def preamble(lang: str) -> str:
    babel = 'ngerman' if lang == 'de' else 'english'
    return (
        r"\documentclass[a4paper,11pt]{article}" "\n"
        r"\usepackage[utf8]{inputenc}" "\n"
        r"\usepackage[T1]{fontenc}" "\n"
        rf"\usepackage[{babel}]{{babel}}" "\n"
        r"\usepackage{lmodern}\usepackage{microtype}" "\n"
        r"\usepackage{amsmath,amssymb,bm,mathtools}" "\n"
        r"\usepackage{geometry}" "\n"
        r"\geometry{a4paper,left=2.3cm,right=2.3cm,top=2.0cm,bottom=2.0cm}" "\n"
        r"\usepackage{booktabs,array}" "\n"
        r"\usepackage{xcolor}\definecolor{bokug}{RGB}{0,135,60}" "\n"
        r"\usepackage{tikz}" "\n"
        r"\usetikzlibrary{patterns,arrows.meta,calc,decorations.pathmorphing}" "\n"
        r"\usepackage{fancyhdr}\pagestyle{fancy}" "\n"
        r"\renewcommand{\headrulewidth}{0.4pt}" "\n"
        r"\usepackage{enumitem}\setlength{\parindent}{0pt}\setlength{\parskip}{4pt}" "\n"
    )


TXT = {
    'de': dict(
        course="VU Mechanik – LAWI 100515 (PI)",
        uni="Universität für Bodenkultur Wien",
        exam="Pr\\\"ufung", group="Gruppe", date="Datum", name="Name / Matrikelnr.",
        given="Gegebenes System",
        givenvals="Gegebene Gr\\\"o\\ss en",
        task="Aufgabenstellung",
        t1="Bestimmen Sie den Grad der statischen Bestimmtheit des Systems.",
        t2="Berechnen Sie s\\\"amtliche Auflagerreaktionen sowie die Gelenkkraft in $C$.",
        t3="Ermitteln Sie alle Stabkr\\\"afte des Fachwerks (Zug/Druck angeben).",
        t4="Zeichnen Sie die Verl\\\"aufe der Schnittgr\\\"o\\ss en $N(x)$, $V(x)$ und $M(x)$ "
           "f\\\"ur den Biegetr\\\"ager $A$--$C$.",
        sys_desc="Das System besteht aus zwei Scheiben, die durch ein Gelenk in $C$ "
                 "verbunden sind: einem Biegetr\\\"ager $A$--$C$ (feste Einspannung in $A$) "
                 "und einem Fachwerk (Rollenlager in $B$).",
        sol="Musterl\\\"osung",
        s_det="Statische Bestimmtheit",
        s_react="Auflagerreaktionen und Gelenkkraft",
        s_truss="Stabkr\\\"afte des Fachwerks",
        s_sect="Schnittgr\\\"o\\ss enverl\\\"aufe des Biegetr\\\"agers $A$--$C$",
        det_txt="Abz\\\"ahlkriterium $n = r - (3 + v)$ mit $r$ Auflagerreaktionen "
                "und $v$ Gelenkbedingungen:",
        determinate="das System ist statisch bestimmt.",
        loadline="Belastung",
    ),
    'en': dict(
        course="VU Mechanik – LAWI 100515 (PI)",
        uni="University of Natural Resources and Life Sciences, Vienna (BOKU)",
        exam="Exam", group="Group", date="Date", name="Name / Student ID",
        given="Given system",
        givenvals="Given quantities",
        task="Tasks",
        t1="Determine the degree of static determinacy of the system.",
        t2="Compute all support reactions and the hinge force at $C$.",
        t3="Determine all member forces of the truss (state tension/compression).",
        t4="Draw the section-force diagrams $N(x)$, $V(x)$ and $M(x)$ for the "
           "bending beam $A$--$C$.",
        sys_desc="The system consists of two rigid bodies connected by a hinge at $C$: "
                 "a bending beam $A$--$C$ (fixed support at $A$) and a truss "
                 "(roller support at $B$).",
        sol="Model solution",
        s_det="Static determinacy",
        s_react="Support reactions and hinge force",
        s_truss="Truss member forces",
        s_sect="Section-force diagrams of the bending beam $A$--$C$",
        det_txt="Counting criterion $n = r - (3 + v)$ with $r$ support reactions "
                "and $v$ hinge conditions:",
        determinate="the system is statically determinate.",
        loadline="Loading",
    ),
}


def header_block(t, group, date_str, semester):
    return (
        r"\fancyhead[L]{\small " + t['course'] + r"}" "\n"
        r"\fancyhead[R]{\small " + semester + r"}" "\n"
        r"\fancyfoot[C]{\thepage}" "\n"
        r"\begin{center}{\large\bfseries\color{bokug}" + t['uni'] + r"}\\[2pt]"
        r"{\large\bfseries " + t['course'] + r"}\\[4pt]"
        rf"{t['exam']} \textbf{{{t['group']} {group}}} \hfill {t['date']}: {date_str}"
        r"\\[2pt]\rule{\linewidth}{0.4pt}\end{center}" "\n"
    )


def given_values(sys: cs.System, lang: str) -> str:
    items = [rf"$a = {fnum(sys.beam_len, lang)}$\,m",
             rf"$\ell = {fnum(sys.panel, lang)}$\,m",
             rf"$h = {fnum(sys.height, lang)}$\,m"]
    if sys.q > 0:
        items.append(rf"$q = {fnum(sys.q, lang)}$\,kN/m")
    for (node, Fx, Fy) in sys.point_loads:
        items.append(rf"$P = {fnum(abs(Fy), lang)}$\,kN")
        if abs(Fx) > 1e-9:
            items.append(rf"$H = {fnum(abs(Fx), lang)}$\,kN")
    return r"\quad ".join(items)


# ════════════════════════════════════════════════════════════════════
#  ASSEMBLE EXAM + SOLUTION
# ════════════════════════════════════════════════════════════════════
def make_exam(sys, lang, group, date_str, semester) -> str:
    t = TXT[lang]
    parts = [preamble(lang), r"\begin{document}",
             header_block(t, group, date_str, semester),
             rf"\textbf{{{t['given']}}}\\[-2pt]", t['sys_desc'],
             tikz_system(sys, show_numbers=True),
             rf"\textbf{{{t['givenvals']}:}}\quad {given_values(sys, lang)}",
             r"\par\medskip",
             rf"\textbf{{{t['task']}}}\par",
             r"\begin{enumerate}[label=\textbf{\arabic*.}]",
             rf"  \item {t['t1']}",
             rf"  \item {t['t2']}",
             rf"  \item {t['t3']}",
             rf"  \item {t['t4']}",
             r"\end{enumerate}",
             r"\end{document}"]
    return "\n".join(parts)


def make_solution(sys, glob, truss, NF, VF, MF, lang, group, date_str, semester) -> str:
    t = TXT[lang]
    a = sys.beam_len
    # determinacy
    r = 3 + 1                      # fixed (3) + roller (1)
    v = 2                          # one hinge -> 2 force unknowns == 2 conditions
    # reaction / hinge components, rotated into the drawn (theta) frame
    th = sys.theta
    Ax, Ay = cs.rot90(th, float(glob['Ax']), float(glob['Ay']))
    Bx, By = cs.rot90(th, 0.0, float(glob['By']))
    Cx, Cy = cs.rot90(th, float(glob['Cx']), float(glob['Cy']))
    react = (
        rf"$A_x = {fnum(Ax, lang)}$\,kN,\quad "
        rf"$A_y = {fnum(Ay, lang)}$\,kN,\quad "
        rf"$M_A = {fnum(float(glob['MA']), lang)}$\,kNm,\quad "
        rf"$B_x = {fnum(Bx, lang)}$\,kN,\quad "
        rf"$B_y = {fnum(By, lang)}$\,kN")
    hinge = (rf"$C_x = {fnum(Cx, lang)}$\,kN,\quad "
             rf"$C_y = {fnum(Cy, lang)}$\,kN")
    parts = [preamble(lang), r"\begin{document}",
             header_block(t, group, date_str, semester),
             rf"\begin{{center}}\textbf{{\large {t['sol']}}}\end{{center}}",
             tikz_system(sys, show_numbers=True),
             # 1 determinacy
             rf"\par\medskip\textbf{{1.\ {t['s_det']}}}\\[-2pt]",
             t['det_txt'],
             rf"\[ n = r - (3+v) = {r} - (3+1) = 0 \quad\Rightarrow\quad "
             rf"\text{{{t['determinate']}}} \]",
             # 2 reactions
             rf"\par\medskip\textbf{{2.\ {t['s_react']}}}\\[-2pt]",
             react + r"\\[2pt]" + hinge + r"\par",
             # 3 truss
             rf"\par\medskip\textbf{{3.\ {t['s_truss']}}}\par",
             truss_table(sys, truss, lang),
             tikz_truss_solution(sys, truss, lang),
             # 4 section forces
             rf"\par\medskip\textbf{{4.\ {t['s_sect']}}}\par",
             r"\begin{center}",
             tikz_diagram(MF, a, 'blue!70!black', r"$M(x)$", lang),
             r"\\[6pt]",
             tikz_diagram(VF, a, 'red!70!black', r"$V(x)$", lang),
             r"\\[6pt]",
             tikz_diagram(NF, a, 'green!45!black', r"$N(x)$", lang),
             r"\end{center}",
             r"\end{document}"]
    return "\n".join(parts)


# ════════════════════════════════════════════════════════════════════
#  COMPILE
# ════════════════════════════════════════════════════════════════════
def write_and_compile(content: str, path: Path, compile_pdf: bool) -> bool:
    path.write_text(content, encoding='utf-8')
    if not compile_pdf:
        return True
    out_dir = path.parent
    cmd = ['pdflatex', '-interaction=nonstopmode', '-halt-on-error',
           f'-output-directory={out_dir}', str(path)]
    ok = True
    for _ in range(2):
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=out_dir)
        if result.returncode != 0:
            print(f"  [LaTeX ERROR] {path.name}")
            log = path.with_suffix('.log')
            if log.exists():
                lines = log.read_text(errors='replace').splitlines()
                errs = [l for l in lines if l.startswith('!') or 'Undefined' in l]
                for e in errs[:12]:
                    print("    " + e)
            ok = False
            break
    for ext in ('.aux', '.log', '.out', '.fls', '.fdb_latexmk'):
        aux = path.with_suffix(ext)
        if aux.exists():
            aux.unlink()
    return ok


# ════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════
def main() -> None:
    ap = argparse.ArgumentParser(description="Random combined beam+truss exam generator")
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--group', default='A')
    ap.add_argument('--date', default='26.06.2026')
    ap.add_argument('--semester', default='SS 2026')
    ap.add_argument('--out', default=str(Path(__file__).parent / 'output'))
    ap.add_argument('--no-compile', action='store_true')
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    compile_pdf = not args.no_compile

    sys = cs.build_system(args.seed)
    res = cs.solve(sys)
    glob, truss = res['glob'], res['truss']
    NF, VF, MF = res['N'], res['V'], res['M']

    print("=" * 60)
    print(f"  Combined beam+truss exam | seed {args.seed} | group {args.group}")
    print(f"  bays={sys.n_panels} ({len(sys.bars)} members)  a={sys.beam_len}  "
          f"l={sys.panel}  h={sys.height}  rotation={sys.theta} deg")
    print(f"  q={sys.q}  point_loads={sys.point_loads}")
    print(f"  A=({fnum(float(glob['Ax']))},{fnum(float(glob['Ay']))})  "
          f"M_A={fnum(float(glob['MA']))}  B_y={fnum(float(glob['By']))}")
    print("=" * 60)

    # "Kombi_" prefix keeps these combined-system files distinct from the
    # single fixed-system generator (generate_exam.py) in the same folder.
    tag = f"seed{args.seed:04d}_Gruppe{args.group}"
    jobs = [
        ('de', 'exam', make_exam(sys, 'de', args.group, args.date, args.semester),
         out / f"Kombi_Klausur_{tag}_DE.tex", "DE Exam"),
        ('en', 'exam', make_exam(sys, 'en', args.group, args.date, args.semester),
         out / f"Kombi_Klausur_{tag}_EN.tex", "EN Exam"),
        ('de', 'sol', make_solution(sys, glob, truss, NF, VF, MF, 'de',
                                     args.group, args.date, args.semester),
         out / f"Kombi_ML_{tag}_DE.tex", "DE Solution"),
        ('en', 'sol', make_solution(sys, glob, truss, NF, VF, MF, 'en',
                                     args.group, args.date, args.semester),
         out / f"Kombi_ML_{tag}_EN.tex", "EN Solution"),
    ]
    for lang, kind, content, path, label in jobs:
        ok = write_and_compile(content, path, compile_pdf)
        pdf = path.with_suffix('.pdf')
        status = "OK " if ok and (pdf.exists() or not compile_pdf) else "FAIL"
        target = pdf if compile_pdf else path
        print(f"  [{label:12s}] {status} -> {target}")


if __name__ == '__main__':
    main()
