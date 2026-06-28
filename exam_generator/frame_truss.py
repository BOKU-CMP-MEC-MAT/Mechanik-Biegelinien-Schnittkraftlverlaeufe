#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
frame_truss.py
==================================================================
General planar **Scheiben** (rigid-body) statics solver for arbitrary
statically determinate systems built from

  * beam Scheiben   – an ordered path of beam segments (may include
                      90-degree corners; carries N, V, M),
  * a truss Scheibe – a pin-jointed, internally rigid truss,

connected by **hinges** (Gelenke, incl. mid-span "half joints") and
held by supports (fixed / pin / roller).  Everything is solved by pure
equilibrium in EXACT rational arithmetic – no FEM, no material data:

  1. 3 equilibrium equations per Scheibe  ->  reactions + hinge forces,
  2. method of joints                     ->  truss member forces,
  3. sectioning of each beam path         ->  N(s), V(s), M(s).

The solver is geometry-agnostic, so beams and the truss may have any
orientation.  Determinacy/stability is verified by the linear solve
(a singular system = mechanism -> rejected by the generator).

Sign conventions: x right, y up; bar force N>0 = tension; beam M>0 =
sagging (tension on the side the local normal points away from).
"""

from __future__ import annotations
import math
from fractions import Fraction as Fr
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

import numpy as np


# ════════════════════════════════════════════════════════════════════
#  MODEL
# ════════════════════════════════════════════════════════════════════
@dataclass
class Support:
    node: str
    kind: str                       # 'fixed' | 'pin' | 'roller'
    normal: Tuple[float, float] = (0.0, 1.0)   # roller reaction direction


@dataclass
class Hinge:
    node: str
    sA: int                         # scheibe id on side A
    sB: int                         # scheibe id on side B


@dataclass
class Scheibe:
    kind: str                       # 'beam' | 'truss'
    path: List[str] = field(default_factory=list)        # beam: ordered nodes
    bars: List[Tuple[str, str]] = field(default_factory=list)   # truss bars
    nodes: List[str] = field(default_factory=list)       # all nodes of scheibe


@dataclass
class Model:
    nodes: Dict[str, Tuple[float, float]]
    scheiben: List[Scheibe]
    supports: List[Support]
    hinges: List[Hinge]
    point_loads: List[Tuple[str, float, float]] = field(default_factory=list)
    # UDL per beam segment: (scheibe_id, segment_index, wx, wy)  [force/length]
    udls: List[Tuple[int, int, float, float]] = field(default_factory=list)

    def xy(self, n):
        return self.nodes[n]


# ════════════════════════════════════════════════════════════════════
#  EXACT LINEAR ALGEBRA
# ════════════════════════════════════════════════════════════════════
def _fr(x) -> Fr:
    return Fr(x).limit_denominator(10**6)


def solve_fraction(A: List[List[Fr]], b: List[Fr]) -> List[Fr]:
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for col in range(n):
        piv = next((r for r in range(col, n) if M[r][col] != 0), None)
        if piv is None:
            raise ValueError("singular system (mechanism / unstable)")
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        M[col] = [v / pv for v in M[col]]
        for r in range(n):
            if r != col and M[r][col] != 0:
                f = M[r][col]
                M[r] = [a_ - f * b_ for a_, b_ in zip(M[r], M[col])]
    return [M[i][n] for i in range(n)]


# ════════════════════════════════════════════════════════════════════
#  GLOBAL EQUILIBRIUM  (reactions + hinge forces)
# ════════════════════════════════════════════════════════════════════
def _owners(m: Model, node: str) -> List[int]:
    return [k for k, s in enumerate(m.scheiben) if node in s.nodes]


def solve_global(m: Model) -> dict:
    nS = len(m.scheiben)
    nrows = 3 * nS

    # --- enumerate unknown columns ----------------------------------
    cols = []          # each: ('sup', support, comp) or ('hinge', hinge, comp)
    for sup in m.supports:
        if sup.kind == 'fixed':
            cols += [('sup', sup, 'Rx'), ('sup', sup, 'Ry'), ('sup', sup, 'M')]
        elif sup.kind == 'pin':
            cols += [('sup', sup, 'Rx'), ('sup', sup, 'Ry')]
        elif sup.kind == 'roller':
            cols += [('sup', sup, 'R')]
    for h in m.hinges:
        cols += [('hinge', h, 'Hx'), ('hinge', h, 'Hy')]

    n = len(cols)
    if n != nrows:
        raise ValueError(f"not determinate: {n} unknowns vs {nrows} equations")

    A = [[Fr(0)] * n for _ in range(nrows)]
    b = [Fr(0)] * nrows

    def add_force(sch_id, fx, fy, px, py, col=None):
        """Force (fx,fy) at (px,py) on scheibe sch_id.
           col given -> coefficient into column; else -> RHS (applied load)."""
        r0 = 3 * sch_id
        moment = px * fy - py * fx
        if col is None:
            b[r0]     -= fx
            b[r0 + 1] -= fy
            b[r0 + 2] -= moment
        else:
            A[r0][col]     += fx
            A[r0 + 1][col] += fy
            A[r0 + 2][col] += moment

    # --- unknown contributions --------------------------------------
    for ci, c in enumerate(cols):
        if c[0] == 'sup':
            _, sup, comp = c
            owner = _owners(m, sup.node)
            sid = owner[0]                      # supports sit on a single scheibe
            px, py = map(_fr, m.nodes[sup.node])
            if comp == 'Rx':
                add_force(sid, Fr(1), Fr(0), px, py, ci)
            elif comp == 'Ry':
                add_force(sid, Fr(0), Fr(1), px, py, ci)
            elif comp == 'M':
                A[3 * sid + 2][ci] += Fr(1)     # pure couple
            elif comp == 'R':
                nx, ny = map(_fr, sup.normal)
                add_force(sid, nx, ny, px, py, ci)
        else:
            _, h, comp = c
            px, py = map(_fr, m.nodes[h.node])
            fx, fy = (Fr(1), Fr(0)) if comp == 'Hx' else (Fr(0), Fr(1))
            add_force(h.sA, fx, fy, px, py, ci)         # +H on side A
            add_force(h.sB, -fx, -fy, px, py, ci)       # -H on side B

    # --- applied loads (RHS) ----------------------------------------
    for (node, fx, fy) in m.point_loads:
        sid = _owners(m, node)[0]
        px, py = map(_fr, m.nodes[node])
        add_force(sid, _fr(fx), _fr(fy), px, py, None)

    for (sid, seg, wx, wy) in m.udls:
        path = m.scheiben[sid].path
        a = np.array(m.nodes[path[seg]]); bb = np.array(m.nodes[path[seg + 1]])
        L = float(np.linalg.norm(bb - a))
        cx, cy = (a + bb) / 2
        add_force(sid, _fr(wx * L), _fr(wy * L), _fr(cx), _fr(cy), None)

    sol = solve_fraction(A, b)

    # --- pack results -----------------------------------------------
    res = {'reactions': {}, 'hinges': {}}
    i = 0
    for c in cols:
        if c[0] == 'sup':
            sup = c[1]
            key = sup.node
            res['reactions'].setdefault(key, {})
            if c[2] == 'R':
                R = sol[i]
                nx, ny = sup.normal
                res['reactions'][key]['Rx'] = R * _fr(nx)
                res['reactions'][key]['Ry'] = R * _fr(ny)
                res['reactions'][key]['R'] = R
            else:
                res['reactions'][key][c[2]] = sol[i]
        else:
            h = c[1]
            res['hinges'].setdefault(h.node, {})
            res['hinges'][h.node][c[2]] = sol[i]
        i += 1
    res['_cols'] = cols
    res['_sol'] = sol
    return res


# ════════════════════════════════════════════════════════════════════
#  TRUSS MEMBER FORCES  (method of joints)
# ════════════════════════════════════════════════════════════════════
def solve_truss(m: Model, glob: dict) -> Dict[Tuple[str, str], float]:
    ts = next((k for k, s in enumerate(m.scheiben) if s.kind == 'truss'), None)
    if ts is None:
        return {}
    sch = m.scheiben[ts]
    jnodes = sch.nodes
    jidx = {nme: k for k, nme in enumerate(jnodes)}
    nb = len(sch.bars)
    A = np.zeros((2 * len(jnodes), nb))
    rhs = np.zeros(2 * len(jnodes))

    for bi, (i, j) in enumerate(sch.bars):
        xi, yi = m.nodes[i]; xj, yj = m.nodes[j]
        dx, dy = xj - xi, yj - yi
        L = math.hypot(dx, dy); ux, uy = dx / L, dy / L
        A[2 * jidx[i], bi] += ux;     A[2 * jidx[i] + 1, bi] += uy
        A[2 * jidx[j], bi] += -ux;    A[2 * jidx[j] + 1, bi] += -uy

    # external forces on the truss: support reactions, hinge forces, loads
    for node, rc in glob['reactions'].items():
        if node in jidx:
            rhs[2 * jidx[node]]     -= float(rc.get('Rx', 0))
            rhs[2 * jidx[node] + 1] -= float(rc.get('Ry', 0))
    for h in m.hinges:
        if ts in (h.sA, h.sB) and h.node in jidx:
            # force ON the truss = +H if truss is side A, -H if side B
            sign = 1.0 if h.sA == ts else -1.0
            Hx = float(glob['hinges'][h.node]['Hx'])
            Hy = float(glob['hinges'][h.node]['Hy'])
            rhs[2 * jidx[h.node]]     -= sign * Hx
            rhs[2 * jidx[h.node] + 1] -= sign * Hy
    for (node, fx, fy) in m.point_loads:
        if node in jidx:
            rhs[2 * jidx[node]]     -= fx
            rhs[2 * jidx[node] + 1] -= fy

    f, *_ = np.linalg.lstsq(A, rhs, rcond=None)
    if float(np.max(np.abs(A @ f - rhs))) > 1e-6:
        raise ValueError("truss not in equilibrium / not solvable")
    return {bar: (0.0 if abs(f[bi]) < 1e-9 else float(f[bi]))
            for bi, bar in enumerate(sch.bars)}


# ════════════════════════════════════════════════════════════════════
#  BEAM SECTION FORCES  N(s), V(s), M(s)  along a beam path
# ════════════════════════════════════════════════════════════════════
def beam_diagrams(m: Model, sid: int, glob: dict, nper: int = 24):
    """Return (s_list, N, V, M, seg_bounds) sampled along the developed
    length of beam scheibe `sid`."""
    sch = m.scheiben[sid]
    path = sch.path
    pts = [np.array(m.nodes[p], dtype=float) for p in path]
    seglen = [float(np.linalg.norm(pts[k + 1] - pts[k])) for k in range(len(pts) - 1)]
    segdir = [(pts[k + 1] - pts[k]) / seglen[k] for k in range(len(pts) - 1)]

    # external nodal forces (and reaction couples) on THIS scheibe
    nodal = {p: np.zeros(2) for p in path}
    nodal_M = {p: 0.0 for p in path}            # concentrated couples at nodes
    for node, rc in glob['reactions'].items():
        if node in nodal and sid in _owners(m, node):
            nodal[node] += np.array([float(rc.get('Rx', 0)), float(rc.get('Ry', 0))])
            nodal_M[node] += float(rc.get('M', 0))     # fixed-support reaction couple
    for h in m.hinges:
        if sid in (h.sA, h.sB) and h.node in nodal:
            sign = 1.0 if h.sA == sid else -1.0
            Hx = float(glob['hinges'][h.node]['Hx']); Hy = float(glob['hinges'][h.node]['Hy'])
            nodal[h.node] += sign * np.array([Hx, Hy])
    for (node, fx, fy) in m.point_loads:
        if node in nodal and sid == _owners(m, node)[0]:
            nodal[node] += np.array([fx, fy])
    # UDL per segment (global vector)
    seg_w = {k: np.zeros(2) for k in range(len(seglen))}
    for (s2, seg, wx, wy) in m.udls:
        if s2 == sid:
            seg_w[seg] += np.array([wx, wy])

    s_axis, Nv, Vv, Mv, bounds = [], [], [], [], [0.0]
    s0 = 0.0
    for k in range(len(seglen)):
        e = segdir[k]
        perp = np.array([-e[1], e[0]])
        for t in np.linspace(0, seglen[k], nper + 1):
            P = pts[k] + e * t
            F = np.zeros(2); Mo = 0.0
            # nodal forces strictly before the cut (nodes 0..k) — node k included
            for idx in range(0, k + 1):
                fp = nodal[path[idx]]
                r = pts[idx] - P
                F += fp; Mo += r[0] * fp[1] - r[1] * fp[0]
                Mo += nodal_M[path[idx]]              # reaction / applied couples
            # full UDL of previous segments
            for j in range(0, k):
                w = seg_w[j]
                if w.any():
                    Lj = seglen[j]; cj = pts[j] + segdir[j] * Lj / 2
                    Wj = w * Lj; r = cj - P
                    F += Wj; Mo += r[0] * Wj[1] - r[1] * Wj[0]
            # partial UDL of current segment [0,t]
            w = seg_w[k]
            if w.any() and t > 0:
                Wt = w * t; cc = pts[k] + e * (t / 2); r = cc - P
                F += Wt; Mo += r[0] * Wt[1] - r[1] * Wt[0]
            # internal forces from the left part:
            #   N>0 tension, V(0+)=+R_up, M>0 sagging
            N = -float(F @ e)
            V = float(F @ perp)
            M = -float(Mo)
            s_axis.append(s0 + t); Nv.append(N); Vv.append(V); Mv.append(M)
        s0 += seglen[k]; bounds.append(s0)
    # clean tiny values
    cl = lambda a: [0.0 if abs(v) < 1e-7 else v for v in a]
    return s_axis, cl(Nv), cl(Vv), cl(Mv), bounds


# ════════════════════════════════════════════════════════════════════
#  FULL SOLVE + CHECKS
# ════════════════════════════════════════════════════════════════════
def solve(m: Model) -> dict:
    glob = solve_global(m)
    truss = solve_truss(m, glob)
    beams = {}
    for sid, s in enumerate(m.scheiben):
        if s.kind == 'beam':
            beams[sid] = beam_diagrams(m, sid, glob)
    _check_global_equilibrium(m, glob)
    return dict(glob=glob, truss=truss, beams=beams)


def _check_global_equilibrium(m: Model, glob: dict, tol=1e-7):
    F = np.zeros(2); Mo = 0.0
    for node, rc in glob['reactions'].items():
        px, py = m.nodes[node]
        f = np.array([float(rc.get('Rx', 0)), float(rc.get('Ry', 0))])
        F += f; Mo += px * f[1] - py * f[0]
        Mo += float(rc.get('M', 0))
    for (node, fx, fy) in m.point_loads:
        px, py = m.nodes[node]
        F += [fx, fy]; Mo += px * fy - py * fx
    for (sid, seg, wx, wy) in m.udls:
        path = m.scheiben[sid].path
        a = np.array(m.nodes[path[seg]]); bb = np.array(m.nodes[path[seg + 1]])
        L = float(np.linalg.norm(bb - a)); c = (a + bb) / 2
        W = np.array([wx, wy]) * L
        F += W; Mo += c[0] * W[1] - c[1] * W[0]
    assert abs(F[0]) < tol and abs(F[1]) < tol and abs(Mo) < tol, \
        f"global equilibrium violated: F={F}, M={Mo}"


# ════════════════════════════════════════════════════════════════════
#  TEST CASES
# ════════════════════════════════════════════════════════════════════
def _mk_beam(nodes, path):
    return Scheibe('beam', path=path, nodes=path)


if __name__ == '__main__':
    # --- Test 1: simply supported beam, UDL ------------------------
    L = 4.0; q = 5.0
    nodes = {'A': (0, 0), 'B': (L, 0)}
    beam = _mk_beam(nodes, ['A', 'B'])
    m = Model(nodes, [beam],
              supports=[Support('A', 'pin'), Support('B', 'roller', (0, 1))],
              hinges=[], point_loads=[], udls=[(0, 0, 0.0, -q)])
    r = solve(m)
    Ay = float(r['glob']['reactions']['A']['Ry'])
    By = float(r['glob']['reactions']['B']['Ry'])
    Mmid = max(r['beams'][0][3]); Vend = r['beams'][0][2][0]
    print(f"T1 simply supported UDL: Ay={Ay:.2f} By={By:.2f} (exp {q*L/2}); "
          f"Mmax={Mmid:.3f} (exp {q*L**2/8}); V(0+)={Vend:.2f} (exp {q*L/2})")

    # --- Test 2: cantilever, tip point load -------------------------
    P = 10.0
    nodes = {'A': (0, 0), 'B': (3, 0)}
    beam = _mk_beam(nodes, ['A', 'B'])
    m = Model(nodes, [beam], supports=[Support('A', 'fixed')],
              hinges=[], point_loads=[('B', 0.0, -P)], udls=[])
    r = solve(m)
    MA = float(r['glob']['reactions']['A']['M'])
    Mroot = r['beams'][0][3][0]
    print(f"T2 cantilever tip load: M_A(reaction)={MA:.2f} (exp {P*3}); "
          f"M(root)={Mroot:.2f} (exp -{P*3} sagging-neg)")

    # --- Test 3: L-frame (corner), horizontal + vertical leg --------
    # A (fixed) at base, up to corner K, then horizontal to tip C with tip load
    nodes = {'A': (0, 0), 'K': (0, 3), 'C': (2, 3)}
    beam = Scheibe('beam', path=['A', 'K', 'C'], nodes=['A', 'K', 'C'])
    m = Model(nodes, [beam], supports=[Support('A', 'fixed')],
              hinges=[], point_loads=[('C', 0.0, -P)], udls=[])
    r = solve(m)
    rc = r['glob']['reactions']['A']
    print(f"T3 L-frame fixed base: A_y={float(rc['Ry']):.2f} (exp {P}), "
          f"M_A={float(rc['M']):.2f} (exp {P*2} = P*horizontal arm)")

    # --- Test 4: Gerber beam (internal hinge) -----------------------
    # A(pin) -- G(hinge) -- B(roller) -- D(roller end), 2 beam Scheiben
    # piece1: A..G  piece2: G..B..D ; UDL on whole, point load at tip
    nodes = {'A': (0, 0), 'G': (2, 0), 'B': (4, 0), 'D': (6, 0)}
    s1 = Scheibe('beam', path=['A', 'G'], nodes=['A', 'G'])
    s2 = Scheibe('beam', path=['G', 'B', 'D'], nodes=['G', 'B', 'D'])
    m = Model(nodes, [s1, s2],
              supports=[Support('A', 'pin'), Support('B', 'roller', (0, 1)),
                        Support('D', 'roller', (0, 1))],
              hinges=[Hinge('G', 0, 1)],
              point_loads=[], udls=[(0, 0, 0.0, -4.0), (1, 0, 0.0, -4.0),
                                    (1, 1, 0.0, -4.0)])
    r = solve(m)
    # M at the hinge G must be ~0 (end of piece 0)
    Mg = r['beams'][0][3][-1]
    print(f"T4 Gerber beam: M at hinge G = {Mg:.4f} (exp 0); "
          f"reactions A={float(r['glob']['reactions']['A']['Ry']):.2f}, "
          f"B={float(r['glob']['reactions']['B']['Ry']):.2f}, "
          f"D={float(r['glob']['reactions']['D']['Ry']):.2f}")

    print("\nAll tests ran (compare printed vs expected).")
