# Exam generators

Two random-exam generators for **VU Mechanik – LAWI 100515 (PI)**.
Both emit German **and** English exam sheets (`Klausur_…`) plus full
worked solutions (`ML_…`) as `.tex` and compiled `.pdf` into `output/`.

## 1. Combined beam + truss systems  (`generate_combined_exam.py`)

Generates **random structural systems** in the style of the course exams:
two Scheiben joined by a single hinge — a **bending beam** (fixed support
at `A`, hinge at `C`) and a **pin-jointed truss** (roller support at `B`).

What is randomised per seed:

* truss size — **2 or 3 panels** (9 or 13 members),
* panel length `ℓ`, truss height `h`, beam length `a`,
* loading — a **UDL** `q` on the beam and/or a **single force** `P`
  (sometimes inclined, with a horizontal part `H`) on a truss node.

The system is **solved from the data, not from hard-coded formulas**
(`combined_system.py`), so every rolled geometry is solved correctly and
exactly:

* global equilibrium (Scheibe method, exact rational arithmetic) →
  support reactions + hinge force,
* method of joints → all truss member forces (tension / compression),
* section method → `N(x)`, `V(x)`, `M(x)` of the beam.

The solver self-checks global equilibrium and the beam end conditions
(`M(0)=M_A`, `M(a)=0`, `V(0)=A_y`) for every system.

```bash
python generate_combined_exam.py --seed 4 --group A \
    --date 26.06.2026 --semester "SS 2026"
# files: output/Kombi_Klausur_seed0004_GruppeA_{DE,EN}.{tex,pdf}
#        output/Kombi_ML_seed0004_GruppeA_{DE,EN}.{tex,pdf}
```

Run the solver self-test (12 seeds, prints reactions + checks):

```bash
python combined_system.py
```

## 2. Single fixed system  (`generate_exam.py`)

The original generator: one fixed topology (cantilever beam + truss,
plus a triangular-load beam) with **randomised loads and dimensions**.

```bash
python generate_exam.py --seed 42 --group A \
    --date 26.06.2026 --semester "SS 2026"
```

## Requirements

* Python 3 with `numpy`
* `pdflatex` with `texlive-latex-extra`, `texlive-fonts-recommended`,
  `texlive-lang-german` (omit compilation with `--no-compile`).
