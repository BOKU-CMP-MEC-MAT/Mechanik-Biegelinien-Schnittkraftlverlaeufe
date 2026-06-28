#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_arbitrary_exam.py
==================================================================
Generates *arbitrary* statically determinate combined systems for
VU Mechanik (LAWI 100515) and renders German/English exam sheets +
full solutions (TikZ -> PDF), built on the general Scheiben solver
``frame_truss.py``.

Variety produced (everything on a 90-degree grid so numbers stay clean):
  * >= 2 beam segments, joined by a rigid 90-degree corner (frame),
    an internal hinge with a point force, or a straight mid node;
  * a truss connected at a beam END or in the MIDDLE ("half joint"),
    with its OWN orientation independent of the beam;
  * always at least one continuous UDL on the beams;
  * supports / loads chosen so the system is determinate & stable
    (verified by the solver; otherwise re-rolled).

Usage:
    python generate_arbitrary_exam.py --seed 7 --group A \
        --date 26.06.2026 --semester "SS 2026"
"""

from __future__ import annotations
import argparse
import math
import random
import subprocess
from pathlib import Path

import frame_truss as ft


# ════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════
def rot(angle: int, x: float, y: float):
    angle %= 360
    return {0: (x, y), 90: (-y, x), 180: (-x, -y), 270: (y, -x)}[angle]


def fnum(v, lang='de', dec=2):
    if abs(v) < 5e-3:
        v = 0.0
    s = f"{v:.{dec}f}".rstrip('0').rstrip('.')
    if s in ('', '-0'):
        s = '0'
    return s.replace('.', ',') if lang == 'de' else s


def Cc(x, y):
    return f"({x:.3f},{y:.3f})"


# ════════════════════════════════════════════════════════════════════
#  WARREN TRUSS BLOCK  (placed & oriented arbitrarily)
# ════════════════════════════════════════════════════════════════════
def truss_block(prefix, conn_name, conn_xy, angle, shape, p, h):
    """Build a determinate truss with 5 or 7 members whose connection
    node is `conn_name` at `conn_xy`, extending in direction `angle`.

      shape 'panel5'  -> single diagonal panel, 5 members (4 joints)
      shape 'warren7' -> two-bay Warren truss, 7 members (5 joints)

    Both expose a hinge connection node (top-left) and a roller node
    (top-right); the truss is only ever loaded at its joints.
    """
    ox, oy = conn_xy

    def G(lx, ly):                       # local -> global (rotated+placed)
        gx, gy = rot(angle, lx, ly)
        return (ox + gx, oy + gy)

    new_nodes, bars = {}, []
    if shape == 'panel5':
        # symmetric lens/diamond (two triangles), connection at the LEFT
        # apex, roller at the RIGHT apex.  Both edges leave the connection
        # diagonally, so the truss extends cleanly perpendicular to the beam
        # without any member lying on the beam axis.
        o1, u0, r = f"{prefix}O1", f"{prefix}U0", f"{prefix}O2"
        new_nodes[o1] = G(p, h / 2)            # upper middle
        new_nodes[u0] = G(p, -h / 2)           # lower middle
        new_nodes[r] = G(2 * p, 0)             # right apex (roller)
        bars = [(conn_name, o1), (conn_name, u0),
                (o1, r), (u0, r), (o1, u0)]
        roller = r
        load_nodes = [u0, o1]
    else:  # warren7
        top = [conn_name, f"{prefix}O1", f"{prefix}O2"]
        bot = [f"{prefix}U0", f"{prefix}U1"]
        new_nodes[top[1]] = G(p, 0)
        new_nodes[top[2]] = G(2 * p, 0)
        new_nodes[bot[0]] = G(0.5 * p, -h)
        new_nodes[bot[1]] = G(1.5 * p, -h)
        bars = [(top[0], top[1]), (top[1], top[2]), (bot[0], bot[1]),
                (top[0], bot[0]), (bot[0], top[1]),
                (top[1], bot[1]), (bot[1], top[2])]
        roller = top[2]
        load_nodes = [bot[0], bot[1]]

    roller_normal = rot(angle, 0.0, 1.0)
    all_nodes = [conn_name] + list(new_nodes.keys())
    return dict(new_nodes=new_nodes, bars=bars, roller=roller,
                roller_normal=roller_normal, bottom=load_nodes,
                nodes=all_nodes)


# ════════════════════════════════════════════════════════════════════
#  RANDOM MODEL BUILDER
# ════════════════════════════════════════════════════════════════════
def build_model(seed: int):
    """Try templates with random parameters until one solves cleanly."""
    rng = random.Random(seed)
    for _attempt in range(400):
        try:
            tmpl = rng.choice(['midspan', 'lframe', 'endspan'])
            model, meta = _build_template(tmpl, rng)
            _orient_fixed_supports(model, meta)      # walls perpendicular to beam
            res = ft.solve(model)
            meta['res'] = res
            meta['template'] = tmpl
            return model, meta
        except Exception:
            continue
    raise RuntimeError("could not build a stable system for this seed")


def _orient_fixed_supports(model, meta):
    """Orient each fixed (clamped) support so its wall is PERPENDICULAR to
    the beam: the 'ground' direction points along the beam axis, away from
    the structure (into the wall)."""
    for sup in model.supports:
        if sup.kind != 'fixed':
            continue
        for sch in model.scheiben:
            if sch.kind == 'beam' and sup.node in sch.path:
                i = sch.path.index(sup.node)
                nb = sch.path[i + 1] if i == 0 else sch.path[i - 1]
                x0, y0 = model.nodes[sup.node]; x1, y1 = model.nodes[nb]
                vx, vy = x0 - x1, y0 - y1            # neighbour -> support
                meta['outdir'][sup.node] = ((1.0 if vx > 0 else -1.0, 0.0)
                                            if abs(vx) >= abs(vy)
                                            else (0.0, 1.0 if vy > 0 else -1.0))
                break


def _truss_params(rng):
    # 5- or 7-member determinate trusses only (so both a Rundschnitt and a
    # Ritterschnitt are always askable); the truss is never carrying a UDL.
    shape = rng.choice(['panel5', 'warren7', 'warren7'])
    p = float(rng.choice([1.5, 2.0]))
    return shape, p, p          # height = panel -> 45-degree diagonals


def _build_template(tmpl, rng):
    a = float(rng.choice([3.0, 4.0]))      # beam segment length unit
    q = float(rng.choice([2, 3, 4, 5]))
    P = float(rng.choice([10, 12, 15, 20]))
    shape, p, h = _truss_params(rng)
    base_angle = rng.choice([0, 90, 180, 270])     # whole-system orientation
    # truss always extends PERPENDICULAR to the beam (one of the two sides),
    # so no truss member ever lies on the beam axis.
    truss_extra = rng.choice([0, 180])
    nodes = {}
    meta = dict(outdir={}, given=[], q=q, P=P, a=a, shape=shape, p=p, h=h,
                base_angle=base_angle, truss_extra=truss_extra, half_joint=False)

    def place(name, lx, ly):
        gx, gy = rot(base_angle, lx, ly)
        nodes[name] = (gx, gy)

    # ---- beam geometry in LOCAL coords, then rotate by base_angle ----
    if tmpl == 'midspan':
        # straight beam P0--P1--P2, truss hangs from the middle (half joint)
        place('P0', 0, 0); place('P1', a, 0); place('P2', 2 * a, 0)
        beam = ft.Scheibe('beam', path=['P0', 'P1', 'P2'],
                          nodes=['P0', 'P1', 'P2'])
        conn = 'P1'
        supports = [ft.Support('P0', 'pin'),
                    ft.Support('P2', 'roller', rot(base_angle, 0, 1))]
        meta['outdir']['P0'] = rot(base_angle, 0, -1)
        meta['outdir']['P2'] = rot(base_angle, 0, -1)
        beam_scheiben = [beam]
        hinges_extra = []
        udls = [(0, rng.randint(0, 1), *rot(base_angle, 0, -q))]
        ploads = []
        meta['half_joint'] = True            # truss pins to the continuous beam

    elif tmpl == 'lframe':
        # L-frame: vertical leg P0->K, horizontal leg K->C ; truss at C
        place('P0', 0, 0); place('K', 0, a); place('C', a, a)
        beam = ft.Scheibe('beam', path=['P0', 'K', 'C'],
                          nodes=['P0', 'K', 'C'])
        conn = 'C'
        supports = [ft.Support('P0', 'fixed')]
        meta['outdir']['P0'] = rot(base_angle, 0, -1)
        beam_scheiben = [beam]
        hinges_extra = []
        udls = [(0, 1, *rot(base_angle, 0, -q))]    # UDL on horizontal leg
        ploads = []

    else:  # endspan: straight cantilever beam P0(fixed)--P1--P2
        place('P0', 0, 0); place('P1', a, 0); place('P2', 2 * a, 0)
        beam = ft.Scheibe('beam', path=['P0', 'P1', 'P2'],
                          nodes=['P0', 'P1', 'P2'])
        supports = [ft.Support('P0', 'fixed')]
        meta['outdir']['P0'] = rot(base_angle, 0, -1)
        beam_scheiben = [beam]
        hinges_extra = []
        if rng.random() < 0.5:
            # HALF JOINT: truss pins to the CONTINUOUS beam at interior P1,
            # the beam runs on to a free tip P2 with a point load
            #  ->  bending moment is NOT zero at the connection.
            conn = 'P1'
            udls = [(0, 0, *rot(base_angle, 0, -q))]
            ploads = [('P2', *rot(base_angle, 0, -P))]
            meta['half_joint'] = True
        else:
            # full hinge at the free beam end P2  (moment = 0 there)
            conn = 'P2'
            udls = [(0, rng.randint(0, 1), *rot(base_angle, 0, -q))]
            ploads = []
            meta['half_joint'] = False

    # ---- truss block at the connection node -------------------------
    tangle = (base_angle + 270 + truss_extra) % 360   # default hang "down"
    tb = truss_block('T', conn, nodes[conn], tangle, shape, p, h)
    nodes.update(tb['new_nodes'])
    truss = ft.Scheibe('truss', bars=tb['bars'], nodes=tb['nodes'])

    n_beam = len(beam_scheiben)
    truss_sid = n_beam
    scheiben = list(beam_scheiben) + [truss]

    # truss roller support
    supports.append(ft.Support(tb['roller'], 'roller', tb['roller_normal']))
    meta['outdir'][tb['roller']] = (-tb['roller_normal'][0], -tb['roller_normal'][1])

    # connection hinge: last beam scheibe that owns conn  <->  truss
    conn_owner = next(i for i, s in enumerate(beam_scheiben) if conn in s.nodes)
    hinges = [ft.Hinge(conn, conn_owner, truss_sid)]
    for (hn, sa, sb) in hinges_extra:
        hinges.append(ft.Hinge(hn, sa, sb))

    # truss point load on a bottom node
    lnode = rng.choice(tb['bottom'])
    Hx = float(rng.choice([0, 0, 5, 8])) if rng.random() < 0.4 else 0.0
    pl = rot(base_angle, Hx, -P)
    ploads.append((lnode, *pl))

    model = ft.Model(nodes, scheiben, supports=supports, hinges=hinges,
                     point_loads=ploads, udls=udls)

    meta.update(beam_sids=list(range(n_beam)), truss_sid=truss_sid,
                conn=conn, roller=tb['roller'], truss=tb,
                given=[rf"$a={fnum(a)}$\,m", rf"$\ell={fnum(p)}$\,m",
                       rf"$h={fnum(h)}$\,m", rf"$q={fnum(q)}$\,kN/m",
                       rf"$P={fnum(P)}$\,kN"])
    return model, meta


# ════════════════════════════════════════════════════════════════════
#  RENDERING  – SYSTEM SKETCH
# ════════════════════════════════════════════════════════════════════
def _support_glyph(xy, kind, outdir):
    """TikZ for a support; outdir points from the node toward the ground
    (axis-aligned). Returns list of draw commands."""
    x, y = xy
    ang = {(0, -1): 0, (-1, 0): 90, (0, 1): 180, (1, 0): 270}.get(
        (round(outdir[0]), round(outdir[1])), 0)

    def R(lx, ly):                       # local (ground-down) -> global
        gx, gy = rot(ang, lx, ly)
        return (x + gx, y + gy)
    L = []
    if kind == 'fixed':
        a1 = R(-0.45, 0.0); a2 = R(0.45, 0.0)
        L.append(rf"  \draw[line width=1.1pt] {Cc(*a1)} -- {Cc(*a2)};")
        for t in [-0.4, -0.2, 0.0, 0.2, 0.4]:
            p1 = R(t, 0.0); p2 = R(t - 0.12, -0.16)
            L.append(rf"  \draw[line width=0.6pt] {Cc(*p1)} -- {Cc(*p2)};")
    elif kind == 'pin':
        t1 = R(-0.26, -0.42); t2 = R(0.26, -0.42)
        L.append(rf"  \draw[thick] {Cc(x, y)} -- {Cc(*t1)} -- {Cc(*t2)} -- cycle;")
        g1 = R(-0.42, -0.42); g2 = R(0.42, -0.42)
        L.append(rf"  \draw[line width=1pt] {Cc(*g1)} -- {Cc(*g2)};")
        for t in [-0.32, -0.12, 0.08, 0.28]:
            p1 = R(t, -0.42); p2 = R(t - 0.1, -0.58)
            L.append(rf"  \draw[line width=0.5pt] {Cc(*p1)} -- {Cc(*p2)};")
    else:  # roller
        t1 = R(-0.26, -0.36); t2 = R(0.26, -0.36)
        L.append(rf"  \draw[thick] {Cc(x, y)} -- {Cc(*t1)} -- {Cc(*t2)} -- cycle;")
        c1 = R(-0.16, -0.46); c2 = R(0.16, -0.46)
        L.append(rf"  \draw[thick] {Cc(*c1)} circle (0.06) {Cc(*c2)} circle (0.06);")
        g1 = R(-0.42, -0.54); g2 = R(0.42, -0.54)
        L.append(rf"  \draw[line width=1pt] {Cc(*g1)} -- {Cc(*g2)};")
    return L


def _bounds(nodes):
    xs = [p[0] for p in nodes.values()]; ys = [p[1] for p in nodes.values()]
    return min(xs), max(xs), min(ys), max(ys)


def _auto_scale(nodes, wmax=13.0, hmax=6.5):
    x0, x1, y0, y1 = _bounds(nodes)
    w = (x1 - x0) + 1.6; h = (y1 - y0) + 1.6     # margin for glyphs/labels
    return max(0.5, min(1.25, wmax / max(w, 0.1), hmax / max(h, 0.1)))


def _halfjoint_pin(nodes, conn, truss_nodes, sc):
    """Position of the half-joint pin: offset a constant ~4pt off the beam
    toward the truss, so the truss pins to a small circle just BELOW the
    continuous beam (the offset is /sc so it stays constant on the page)."""
    cx, cy = nodes[conn]
    others = [n for n in truss_nodes if n != conn]
    mx = sum(nodes[n][0] for n in others) / len(others)
    my = sum(nodes[n][1] for n in others) / len(others)
    dx, dy = mx - cx, my - cy
    d = math.hypot(dx, dy) or 1.0
    off = 0.14 / sc
    return (cx + dx / d * off, cy + dy / d * off)


def tikz_system(model, meta, with_numbers=True):
    nodes = model.nodes
    sc = _auto_scale(nodes)
    L = [r"\begin{center}",
         rf"\begin{{tikzpicture}}[scale={sc:.3f},>=Stealth,line join=round]"]
    for nme, (x, y) in nodes.items():
        L.append(rf"  \coordinate ({nme}) at {Cc(x, y)};")
    truss = meta['truss']
    conn = meta['conn']
    half = meta.get('half_joint', False)
    # For a HALF JOINT the truss pins to a small circle a little BELOW the
    # continuous beam; the truss members start from that offset pin (CPIN).
    if half:
        pin = _halfjoint_pin(nodes, conn, truss['nodes'], sc)
        L.append(rf"  \coordinate (CPIN) at {Cc(*pin)};")
    pin_of = lambda n: 'CPIN' if (half and n == conn) else n

    # truss bars
    for (i, j) in truss['bars']:
        L.append(rf"  \draw[thick] ({pin_of(i)}) -- ({pin_of(j)});")
    # beam segments (heavy, continuous through the connection)
    for sid in meta['beam_sids']:
        path = model.scheiben[sid].path
        for k in range(len(path) - 1):
            L.append(rf"  \draw[line width=2.2pt] ({path[k]}) -- ({path[k+1]});")
    # truss joints (the connection node has its own symbol)
    for nme in truss['nodes']:
        if nme == conn:
            continue
        L.append(rf"  \fill ({nme}) circle (1.6pt);")
    # connection symbol
    if half:
        # half joint: hollow pin just below the (continuous) beam
        L.append(rf"  \draw[fill=white,line width=0.9pt] (CPIN) circle (2.6pt);")
    else:
        # full hinge at a beam END (moment = 0 there): white-filled circle
        L.append(rf"  \draw[fill=white,line width=1pt] ({conn}) circle (3.2pt);")
    # supports
    for sup in model.supports:
        L += _support_glyph(nodes[sup.node], sup.kind, meta['outdir'][sup.node])
    # member numbers on truss
    if with_numbers:
        for bi, (i, j) in enumerate(truss['bars']):
            pi = pin if (half and i == conn) else nodes[i]
            pj = pin if (half and j == conn) else nodes[j]
            mx = (pi[0] + pj[0]) / 2; my = (pi[1] + pj[1]) / 2
            L.append(rf"  \node[circle,fill=white,draw=gray!55,inner sep=0.5pt,"
                     rf"font=\scriptsize] at ({mx:.3f},{my:.3f}) {{{bi+1}}};")
    # UDL arrows on beam segments
    for (sid, seg, wx, wy) in model.udls:
        path = model.scheiben[sid].path
        a = nodes[path[seg]]; b = nodes[path[seg + 1]]
        mag = math.hypot(wx, wy); ux, uy = wx / mag, wy / mag
        off = 0.62
        steps = 6
        for s in range(steps + 1):
            bx = a[0] + (b[0] - a[0]) * s / steps
            by = a[1] + (b[1] - a[1]) * s / steps
            sx, sy = bx - ux * off, by - uy * off
            L.append(rf"  \draw[->,blue!70!black] {Cc(sx, sy)} -- {Cc(bx-ux*0.06, by-uy*0.06)};")
        mx = (a[0] + b[0]) / 2 - ux * off; my = (a[1] + b[1]) / 2 - uy * off
        L.append(rf"  \draw[blue!70!black,thick] {Cc(a[0]-ux*off, a[1]-uy*off)} -- "
                 rf"{Cc(b[0]-ux*off, b[1]-uy*off)};")
        L.append(rf"  \node[blue!70!black] at {Cc(mx-ux*0.25, my-uy*0.25)} {{$q$}};")
    # point loads
    for (node, fx, fy) in model.point_loads:
        mag = math.hypot(fx, fy)
        if mag < 1e-9:
            continue
        ux, uy = fx / mag, fy / mag
        nx, ny = nodes[node]
        sx, sy = nx - ux * 0.95, ny - uy * 0.95
        L.append(rf"  \draw[->,red!80!black,line width=1.1pt] {Cc(sx, sy)} -- {Cc(nx, ny)};")
        L.append(rf"  \node[red!80!black] at {Cc(sx-ux*0.18, sy-uy*0.18)} {{$P$}};")
    # node labels
    for nme in nodes:
        lab = _node_label(nme, model, meta)
        if lab:
            L.append(rf"  \node[font=\small] at {Cc(nodes[nme][0], nodes[nme][1])} "
                     rf"[xshift=-7pt,yshift=7pt] {{{lab}}};")
    L += [r"\end{tikzpicture}", r"\end{center}"]
    return "\n".join(L)


def _node_label(nme, model, meta):
    if nme == meta['roller']:
        return "$B$"
    if nme in ('P0',):
        return "$A$"
    if nme == 'K':
        return "$K$"
    if nme == 'G':
        return "$G$"
    if nme == meta['conn']:
        return "$C$"
    if nme in ('P1', 'P2', 'D'):
        return "$D$"
    return ""


# ════════════════════════════════════════════════════════════════════
#  RENDERING  – DIAGRAMS & TRUSS
# ════════════════════════════════════════════════════════════════════
def tikz_beam_diagram(s, vals, color, title, lang, bounds):
    vmax = max((abs(v) for v in vals), default=0.0)
    smax = s[-1] if s else 1.0
    if vmax < 1e-9:
        return ("\n".join([
            r"\begin{tikzpicture}[>=Stealth]",
            rf"  \draw[->] (-0.2,0) -- ({8.4:.2f},0) node[below right]{{$s$}};",
            rf"  \draw[{color},very thick] (0,0) -- (8,0);",
            rf"  \node[{color},right] at (8.2,0.3) {{{title}\,$\equiv 0$}};",
            r"\end{tikzpicture}"]))
    W, Hh = 8.0, 1.15
    sx = W / smax; sy = Hh / vmax
    coords = " ".join(f"({x*sx:.3f},{v*sy:.3f})" for x, v in zip(s, vals))
    imax = max(range(len(vals)), key=lambda k: vals[k])
    imin = min(range(len(vals)), key=lambda k: vals[k])
    L = [r"\begin{tikzpicture}[>=Stealth]",
         rf"  \draw[->] (-0.2,0) -- ({W+0.35:.2f},0) node[below right]{{$s$}};",
         rf"  \filldraw[fill={color}!12,draw={color},thick] (0,0) -- "
         rf"plot coordinates {{{coords}}} -- ({W:.3f},0) -- cycle;"]
    for b in bounds[1:-1]:
        L.append(rf"  \draw[gray,dashed,thin] ({b*sx:.3f},-{Hh:.2f}) -- ({b*sx:.3f},{Hh:.2f});")
    for idx, anch in ((imax, 'above'), (imin, 'below')):
        if abs(vals[idx]) > 1e-3 * vmax:
            L.append(rf"  \node[{anch},{color},font=\footnotesize] at "
                     rf"({s[idx]*sx:.3f},{vals[idx]*sy:.3f}) {{{fnum(vals[idx],lang,1)}}};")
    L.append(rf"  \node[{color},right] at ({W+0.5:.2f},0.32) {{{title}}};")
    L.append(r"\end{tikzpicture}")
    return "\n".join(L)


def tikz_truss_solution(model, meta, forces, lang):
    nodes = model.nodes; truss = meta['truss']
    sc = _auto_scale(nodes)
    L = [r"\begin{center}",
         rf"\begin{{tikzpicture}}[scale={sc:.3f},>=Stealth,line join=round]"]
    for nme, (x, y) in nodes.items():
        L.append(rf"  \coordinate ({nme}) at {Cc(x, y)};")
    conn = meta['conn']; half = meta.get('half_joint', False)
    if half:
        pin = _halfjoint_pin(nodes, conn, truss['nodes'], sc)
        L.append(rf"  \coordinate (CPIN) at {Cc(*pin)};")
    pin_of = lambda n: 'CPIN' if (half and n == conn) else n
    for (i, j) in truss['bars']:
        f = forces[(i, j)]
        col = 'red!75!black' if f > 1e-6 else ('blue!70!black' if f < -1e-6 else 'gray')
        L.append(rf"  \draw[thick,{col}] ({pin_of(i)}) -- ({pin_of(j)});")
    for sid in meta['beam_sids']:
        path = model.scheiben[sid].path
        for k in range(len(path) - 1):
            L.append(rf"  \draw[line width=2pt] ({path[k]}) -- ({path[k+1]});")
    for nme in truss['nodes']:
        if nme == conn:
            continue
        L.append(rf"  \fill ({nme}) circle (1.6pt);")
    if half:
        L.append(rf"  \draw[fill=white,line width=0.9pt] (CPIN) circle (2.6pt);")
    for bi, (i, j) in enumerate(truss['bars']):
        pi = pin if (half and i == conn) else nodes[i]
        pj = pin if (half and j == conn) else nodes[j]
        mx = (pi[0] + pj[0]) / 2; my = (pi[1] + pj[1]) / 2
        L.append(rf"  \node[circle,fill=white,draw=gray!55,inner sep=0.5pt,"
                 rf"font=\scriptsize] at ({mx:.3f},{my:.3f}) {{{bi+1}}};")
    leg = ("rot: Zug $(+)$\\quad blau: Druck $(-)$" if lang == 'de'
           else "red: tension $(+)$\\quad blue: compression $(-)$")
    x0, x1, y0, y1 = _bounds(nodes)
    L.append(rf"  \node[font=\footnotesize] at ({(x0+x1)/2:.2f},{y1+0.7:.2f}) {{{leg}}};")
    L += [r"\end{tikzpicture}", r"\end{center}"]
    return "\n".join(L)


def truss_table(model, meta, forces, lang):
    truss = meta['truss']
    hn = "Stab" if lang == 'de' else "Member"
    hf = "Stabkraft $S$ [kN]" if lang == 'de' else "Force $S$ [kN]"
    ht = "Art" if lang == 'de' else "Type"
    zd = (("Zug", "Druck", "Nullstab") if lang == 'de'
          else ("tension", "compression", "zero"))
    rows = []
    for bi, (i, j) in enumerate(truss['bars']):
        f = forces[(i, j)]
        t = zd[0] if f > 1e-6 else (zd[1] if f < -1e-6 else zd[2])
        rows.append(rf"  {bi+1} & {fnum(f,lang,2)} & {t} \\")
    return (r"\begin{center}\renewcommand{\arraystretch}{1.1}\begin{tabular}{c r l}"
            "\n\\toprule\n" rf"{hn} & {hf} & {ht} \\" "\n\\midrule\n"
            + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\\end{center}")


# ════════════════════════════════════════════════════════════════════
#  LATEX DOCUMENT
# ════════════════════════════════════════════════════════════════════
def preamble(lang):
    babel = 'ngerman' if lang == 'de' else 'english'
    return (
        r"\documentclass[a4paper,11pt]{article}" "\n"
        r"\usepackage[utf8]{inputenc}\usepackage[T1]{fontenc}" "\n"
        rf"\usepackage[{babel}]{{babel}}\usepackage{{lmodern}}\usepackage{{microtype}}" "\n"
        r"\usepackage{amsmath,amssymb}\usepackage{geometry}" "\n"
        r"\geometry{a4paper,left=2.2cm,right=2.2cm,top=2.0cm,bottom=2.0cm}" "\n"
        r"\usepackage{booktabs,array}\usepackage{xcolor}" "\n"
        r"\definecolor{bokug}{RGB}{0,135,60}\usepackage{tikz}" "\n"
        r"\usetikzlibrary{arrows.meta,calc}" "\n"
        r"\usepackage{fancyhdr}\pagestyle{fancy}" "\n"
        r"\renewcommand{\headrulewidth}{0.4pt}" "\n"
        r"\usepackage{enumitem}\setlength{\parindent}{0pt}\setlength{\parskip}{4pt}" "\n")


TXT = {
    'de': dict(uni="Universität für Bodenkultur Wien",
               course="VU Mechanik – LAWI 100515 (PI)", exam="Prüfung",
               group="Gruppe", date="Datum", given="Gegebenes System",
               givenv="Gegebene Größen", task="Aufgabenstellung", sol="Musterlösung",
               desc="Das ebene System besteht aus Biegeträgern und einem Fachwerk, "
                    "die durch Gelenke verbunden sind.",
               t=["Bestimmen Sie den Grad der statischen Bestimmtheit.",
                  "Berechnen Sie alle Auflagerreaktionen und Gelenkkräfte.",
                  "Ermitteln Sie alle Stabkräfte des Fachwerks (Zug/Druck).",
                  "Zeichnen Sie die Schnittgrößen $N$, $V$, $M$ der Biegeträger."],
               d1="Statische Bestimmtheit", d2="Auflagerreaktionen und Gelenkkräfte",
               d3="Stabkräfte des Fachwerks", d4="Schnittgrößenverläufe der Biegeträger",
               det="Abzählkriterium $n=3k-(a+z)$ (Scheiben $k$, Reaktionen $a$, "
                   "Zwischenreaktionen $z$):", determ="statisch bestimmt",
               beam="Biegeträger"),
    'en': dict(uni="University of Natural Resources and Life Sciences, Vienna (BOKU)",
               course="VU Mechanik – LAWI 100515 (PI)", exam="Exam",
               group="Group", date="Date", given="Given system",
               givenv="Given quantities", task="Tasks", sol="Model solution",
               desc="The planar system consists of bending beams and a truss "
                    "connected by hinges.",
               t=["Determine the degree of static determinacy.",
                  "Compute all support reactions and hinge forces.",
                  "Determine all truss member forces (tension/compression).",
                  "Draw the section forces $N$, $V$, $M$ of the bending beams."],
               d1="Static determinacy", d2="Support reactions and hinge forces",
               d3="Truss member forces", d4="Section-force diagrams of the beams",
               det="Counting criterion $n=3k-(a+z)$ (bodies $k$, reactions $a$, "
                   "interaction forces $z$):", determ="statically determinate",
               beam="Beam"),
}


def header(t, group, date_str, semester):
    return (r"\fancyhead[L]{\small " + t['course'] + r"}\fancyhead[R]{\small "
            + semester + r"}\fancyfoot[C]{\thepage}" "\n"
            r"\begin{center}{\large\bfseries\color{bokug}" + t['uni'] + r"}\\[2pt]"
            r"{\large\bfseries " + t['course'] + r"}\\[4pt]"
            + f"{t['exam']} \\textbf{{{t['group']} {group}}} \\hfill {t['date']}: {date_str}"
            + r"\\[2pt]\rule{\linewidth}{0.4pt}\end{center}" "\n")


def make_exam(model, meta, lang, group, date_str, semester):
    t = TXT[lang]
    parts = [preamble(lang), r"\begin{document}", header(t, group, date_str, semester),
             rf"\textbf{{{t['given']}}}\par {t['desc']}",
             tikz_system(model, meta, True),
             rf"\textbf{{{t['givenv']}:}}\quad " + r"\quad ".join(meta['given']),
             r"\par\medskip", rf"\textbf{{{t['task']}}}\par",
             r"\begin{enumerate}[label=\textbf{\arabic*.}]"]
    for ti in t['t']:
        parts.append(rf"  \item {ti}")
    parts += [r"\end{enumerate}", r"\end{document}"]
    return "\n".join(parts)


def make_solution(model, meta, lang, group, date_str, semester):
    t = TXT[lang]; res = meta['res']; glob = res['glob']
    k = len(model.scheiben)
    a_cnt = sum({'fixed': 3, 'pin': 2, 'roller': 1}[s.kind] for s in model.supports)
    z_cnt = 2 * len(model.hinges)
    n_det = 3 * k - (a_cnt + z_cnt)
    # reactions text
    rlines = []
    for node, rc in glob['reactions'].items():
        lab = _node_label(node, model, meta).strip('$') or node
        comp = [rf"R_x={fnum(float(rc.get('Rx',0)),lang)}",
                rf"R_y={fnum(float(rc.get('Ry',0)),lang)}"]
        if 'M' in rc:
            comp.append(rf"M={fnum(float(rc['M']),lang)}")
        rlines.append(rf"${lab}:\ " + ",\\ ".join(comp) + r"$")
    hlines = []
    for hn, hc in glob['hinges'].items():
        lab = _node_label(hn, model, meta).strip('$') or hn
        hlines.append(rf"${lab}:\ H_x={fnum(float(hc['Hx']),lang)},\ "
                      rf"H_y={fnum(float(hc['Hy']),lang)}$")
    parts = [preamble(lang), r"\begin{document}", header(t, group, date_str, semester),
             rf"\begin{{center}}\textbf{{\large {t['sol']}}}\end{{center}}",
             tikz_system(model, meta, True),
             rf"\par\medskip\textbf{{1.\ {t['d1']}}}\par {t['det']}",
             rf"\[ n=3k-(a+z)=3\cdot{k}-({a_cnt}+{z_cnt})={n_det}"
             rf"\ \Rightarrow\ \text{{{t['determ']}}} \]",
             rf"\par\medskip\textbf{{2.\ {t['d2']}}}\par",
             r"\quad ".join(rlines) + r"\par " + r"\quad ".join(hlines),
             rf"\par\medskip\textbf{{3.\ {t['d3']}}}\par",
             truss_table(model, meta, res['truss'], lang),
             tikz_truss_solution(model, meta, res['truss'], lang),
             rf"\par\medskip\textbf{{4.\ {t['d4']}}}\par", r"\begin{center}"]
    cols = ['blue!70!black', 'red!70!black', 'green!45!black']
    titles = ['$M(s)$', '$V(s)$', '$N(s)$']
    for bi, sid in enumerate(meta['beam_sids']):
        s, N, V, M, bounds = res['beams'][sid]
        if len(meta['beam_sids']) > 1:
            parts.append(rf"\textbf{{{t['beam']} {bi+1}}}\\[2pt]")
        parts.append(tikz_beam_diagram(s, M, cols[0], titles[0], lang, bounds) + r"\\[5pt]")
        parts.append(tikz_beam_diagram(s, V, cols[1], titles[1], lang, bounds) + r"\\[5pt]")
        parts.append(tikz_beam_diagram(s, N, cols[2], titles[2], lang, bounds) + r"\\[10pt]")
    parts += [r"\end{center}", r"\end{document}"]
    return "\n".join(parts)


# ════════════════════════════════════════════════════════════════════
#  COMPILE / MAIN
# ════════════════════════════════════════════════════════════════════
def write_and_compile(content, path, compile_pdf):
    path.write_text(content, encoding='utf-8')
    if not compile_pdf:
        return True
    out_dir = path.parent
    cmd = ['pdflatex', '-interaction=nonstopmode', '-halt-on-error',
           f'-output-directory={out_dir}', str(path)]
    ok = True
    for _ in range(2):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=out_dir)
        if r.returncode != 0:
            print(f"  [LaTeX ERROR] {path.name}")
            log = path.with_suffix('.log')
            if log.exists():
                for e in [l for l in log.read_text(errors='replace').splitlines()
                          if l.startswith('!')][:8]:
                    print("    " + e)
            ok = False
            break
    for ext in ('.aux', '.log', '.out'):
        p = path.with_suffix(ext)
        if p.exists():
            p.unlink()
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--group', default='A')
    ap.add_argument('--date', default='26.06.2026')
    ap.add_argument('--semester', default='SS 2026')
    ap.add_argument('--out', default=str(Path(__file__).parent / 'output'))
    ap.add_argument('--no-compile', action='store_true')
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    compile_pdf = not args.no_compile

    model, meta = build_model(args.seed)
    print("=" * 60)
    print(f"  Arbitrary system | seed {args.seed} | template={meta['template']} "
          f"| base={meta['base_angle']} truss_rot={meta['truss_extra']}")
    print(f"  scheiben={len(model.scheiben)} supports={len(model.supports)} "
          f"hinges={len(model.hinges)} truss_members={len(meta['truss']['bars'])}")
    print("=" * 60)

    tag = f"seed{args.seed:04d}_Gruppe{args.group}"
    jobs = [
        (make_exam(model, meta, 'de', args.group, args.date, args.semester),
         out / f"Arb_Klausur_{tag}_DE.tex", "DE Exam"),
        (make_exam(model, meta, 'en', args.group, args.date, args.semester),
         out / f"Arb_Klausur_{tag}_EN.tex", "EN Exam"),
        (make_solution(model, meta, 'de', args.group, args.date, args.semester),
         out / f"Arb_ML_{tag}_DE.tex", "DE Solution"),
        (make_solution(model, meta, 'en', args.group, args.date, args.semester),
         out / f"Arb_ML_{tag}_EN.tex", "EN Solution"),
    ]
    for content, path, label in jobs:
        ok = write_and_compile(content, path, compile_pdf)
        tgt = path.with_suffix('.pdf') if compile_pdf else path
        print(f"  [{label:12s}] {'OK ' if ok else 'FAIL'} -> {tgt}")


if __name__ == '__main__':
    main()
