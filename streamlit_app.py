import streamlit as st
import random
import numpy as np
import matplotlib.pyplot as plt

# ==============================================================================
# EINSTELLUNGEN: VORZEICHEN- UND DARSTELLUNGSKONVENTION
# ==============================================================================
KONVENTION = {
    'V_vorzeichen_drehen': False,  
    'V_positiv_nach_unten': True, 
    'M_vorzeichen_drehen': False,  
    'M_positiv_nach_unten': True,  
    'w_vorzeichen_drehen': False,  
    'w_positiv_nach_unten': True   
}

# ==============================================================================
# HIGH-SPEED FEM-SOLVER (Finite Elemente Methode)
# ==============================================================================
def berechne_fem(L, fixed, pinned, rollers, hinges, F_val, F_pos, q_val, q_start, q_end):
    """Löst das Balkensystem über die Finite Elemente Methode in Millisekunden."""
    N = int(L * 100)
    dx = L / N
    x_vals = np.linspace(0, L, N+1)
    
    EI = 210e6 * 5e-5

    k_e = (EI / dx**3) * np.array([
        [ 12,     6*dx,   -12,     6*dx],
        [ 6*dx,  4*dx**2, -6*dx, 2*dx**2],
        [-12,    -6*dx,    12,    -6*dx],
        [ 6*dx,  2*dx**2, -6*dx, 4*dx**2]
    ])

    is_hinge = np.zeros(N+1, dtype=bool)
    for h in hinges:
        idx = int(round(h / dx))
        is_hinge[idx] = True

    dof_w = np.zeros(N+1, dtype=int)
    dof_t_L = np.zeros(N+1, dtype=int)
    dof_t_R = np.zeros(N+1, dtype=int)

    curr_dof = 0
    for i in range(N+1):
        dof_w[i] = curr_dof; curr_dof += 1
        dof_t_L[i] = curr_dof; curr_dof += 1
        if is_hinge[i]:
            dof_t_R[i] = curr_dof; curr_dof += 1
        else:
            dof_t_R[i] = dof_t_L[i]

    K = np.zeros((curr_dof, curr_dof))
    F_vec = np.zeros(curr_dof)

    for i in range(N):
        idx = [dof_w[i], dof_t_R[i], dof_w[i+1], dof_t_L[i+1]]
        for r in range(4):
            for c in range(4):
                K[idx[r], idx[c]] += k_e[r, c]

    if F_val > 0:
        idx_p = int(round(F_pos / dx))
        F_vec[dof_w[idx_p]] -= F_val

    if q_val > 0:
        idx_qs = int(round(q_start / dx))
        idx_qe = int(round(q_end / dx))
        for i in range(idx_qs, idx_qe):
            F_vec[dof_w[i]] += -q_val * dx / 2
            F_vec[dof_t_R[i]] += -q_val * dx**2 / 12
            F_vec[dof_w[i+1]] += -q_val * dx / 2
            F_vec[dof_t_L[i+1]] += q_val * dx**2 / 12

    PENALTY = 1e12
    for sp in pinned + rollers:
        idx = int(round(sp / dx))
        K[dof_w[idx], dof_w[idx]] += PENALTY

    for fp in fixed:
        idx = int(round(fp / dx))
        K[dof_w[idx], dof_w[idx]] += PENALTY
        K[dof_t_L[idx], dof_t_L[idx]] += PENALTY
        K[dof_t_R[idx], dof_t_R[idx]] += PENALTY

    U = np.linalg.solve(K, F_vec)
    
    if np.max(np.abs(U)) > 1000:
        raise np.linalg.LinAlgError("Mechanismus erkannt!")

    w_vals = U[dof_w] 
    V_vals = np.zeros(N+1)
    M_vals = np.zeros(N+1)

    idx_qs = int(round(q_start / dx)) if q_val > 0 else -1
    idx_qe = int(round(q_end / dx)) if q_val > 0 else -1

    for i in range(N):
        idx = [dof_w[i], dof_t_R[i], dof_w[i+1], dof_t_L[i+1]]
        u_e = U[idx]
        
        f_e_fixed = np.zeros(4)
        if idx_qs <= i < idx_qe:
            f_e_fixed = np.array([q_val*dx/2, q_val*dx**2/12, q_val*dx/2, -q_val*dx**2/12])
            
        f_e = (k_e @ u_e) + f_e_fixed
        V_vals[i] = f_e[0]
        M_vals[i] = -f_e[1]

    V_vals[N] = -f_e[2]
    M_vals[N] = f_e[3]
    
    w_vals = -w_vals * 1000
    if KONVENTION['V_vorzeichen_drehen']: V_vals = -V_vals
    if KONVENTION['M_vorzeichen_drehen']: M_vals = -M_vals
    if KONVENTION['w_vorzeichen_drehen']: w_vals = -w_vals

    V_vals[np.abs(V_vals) < 1e-4] = 0.0
    M_vals[np.abs(M_vals) < 1e-4] = 0.0
    w_vals[np.abs(w_vals) < 1e-4] = 0.0

    return x_vals, V_vals, M_vals, w_vals

# ==============================================================================
# ZUFALLS-GENERATOR (Robuster Brute-Force Ansatz)
# ==============================================================================
def generiere_stabiles_zufallssystem():
    """Würfelt wild Systeme, bis der FEM-Solver ein stabiles absegnet."""
    while True:
        anzahl_felder = random.randint(3, 5)
        feld_laengen = [random.randint(3, 5) for _ in range(anzahl_felder)]
        knoten = [0]
        for l in feld_laengen: knoten.append(knoten[-1] + l)
        L = knoten[-1]
        
        fixed = []; pinned = []; rollers = []; hinges = []
        
        if random.choice([True, False]): fixed.append(knoten[0])
        else: pinned.append(knoten[0])
        
        for k in knoten[1:-1]: rollers.append(k)
            
        if random.choice([True, False]): fixed.append(knoten[-1])
        else: rollers.append(knoten[-1])
            
        # Optionaler Kragarm links
        if not fixed and random.random() > 0.5:
            pinned.pop(0)
            rollers.insert(0, knoten[1]) 
            pinned.append(rollers.pop(1))
            
        max_hinges = len(fixed)*2 + len(pinned) + len(rollers) - 2
        if max_hinges > 0:
            anzahl_hinges = random.randint(0, min(max_hinges, 3))
            moegliche_hinges = []
            for i in range(anzahl_felder):
                start = knoten[i]; ende = knoten[i+1]
                if ende - start >= 4:
                    moegliche_hinges.extend([start+1, ende-1])
            random.shuffle(moegliche_hinges)
            hinges = moegliche_hinges[:anzahl_hinges]
            
        q_feld = random.randint(0, anzahl_felder-1)
        q_start = knoten[q_feld]
        q_end = knoten[q_feld+1]
        
        verboten = fixed + pinned + rollers + hinges + list(range(q_start, q_end+1))
        erlaubt = [x for x in range(1, L) if x not in verboten]
        
        F_pos = random.choice(erlaubt) if erlaubt else 0
        F_val = random.randint(2, 6) * 10
        q_val = random.randint(2, 5) * 5
        if F_pos == 0: F_val = 0
        
        try:
            berechne_fem(L, fixed, pinned, rollers, hinges, F_val, F_pos, q_val, q_start, q_end)
            sys_info = f"Zufallssystem ({anzahl_felder} Felder)"
            return L, fixed, pinned, rollers, hinges, F_val, F_pos, q_val, q_start, q_end, sys_info
        except np.linalg.LinAlgError:
            continue

# ==============================================================================
# ZEICHNEN UND AUSGABE
# ==============================================================================
def zeichne_schaltbild(ax, L, fixed, pinned, rollers, hinges, F_val, F_pos, q_val, q_start, q_end):
    ax.plot([0, L], [0, 0], color='black', linewidth=4, zorder=1)
    ax.set_xlim(-0.5, L + 0.5)
    ax.set_ylim(-1.5, 2.5)
    ax.axis('off')

    for pos in fixed:
        if pos == 0:
            ax.plot([0, 0], [-0.8, 0.8], 'k-', lw=3, zorder=2)
            for i in np.linspace(-0.8, 0.8, 6): ax.plot([-0.2, 0], [i-0.1, i], 'k-', lw=1, zorder=2)
        elif pos == L:
            ax.plot([L, L], [-0.8, 0.8], 'k-', lw=3, zorder=2)
            for i in np.linspace(-0.8, 0.8, 6): ax.plot([L, L+0.2], [i, i-0.1], 'k-', lw=1, zorder=2)

    for pos in pinned:
        ax.plot(pos, -0.2, '^', color='black', markersize=12, zorder=2)
        ax.plot([pos-0.3, pos+0.3], [-0.4, -0.4], 'k-', lw=2, zorder=2)
        for j in np.linspace(-0.3, 0.3, 4): ax.plot([pos+j-0.1, pos+j], [-0.5, -0.4], 'k-', lw=1, zorder=2)

    for pos in rollers:
        ax.plot(pos, -0.2, '^', color='black', markersize=12, zorder=2)
        ax.plot([pos-0.3, pos+0.3], [-0.4, -0.4], 'k-', lw=2, zorder=2)
        ax.plot([pos-0.3, pos+0.3], [-0.5, -0.5], 'k-', lw=2, zorder=2)

    for h in hinges:
        ax.plot(h, 0, 'o', color='white', markeredgecolor='black', markersize=9, markeredgewidth=2, zorder=3)

    if F_val > 0:
        ax.arrow(F_pos, 1.5, 0, -1.2, head_width=0.2, head_length=0.3, fc='red', ec='red', lw=2)
        ax.text(F_pos, 1.7, f"F={F_val} kN", ha='center', color='red', fontweight='bold')

    if q_val > 0:
        ax.plot([q_start, q_end], [1.0, 1.0], 'b-', lw=2)
        for x in range(q_start, q_end + 1):
            ax.arrow(x, 1.0, 0, -0.7, head_width=0.15, head_length=0.2, fc='blue', ec='blue')
        ax.text((q_start+q_end)/2, 1.2, f"q={q_val} kN/m", ha='center', color='blue', fontweight='bold')

def plot_verlauf(ax, x, y, farbe, invertiere_y=False):
    ax.plot(x, y, color=farbe, linewidth=2)
    ax.fill_between(x, y, 0, color=farbe, alpha=0.15)
    ax.axhline(0, color='black', linewidth=1.5) 
    ax.grid(True, linestyle=':', alpha=0.7)
    ax.set_xlim(0, x[-1])
    
    idx_max = np.argmax(y)
    idx_min = np.argmin(y)
    
    va_max = 'bottom' if not invertiere_y else 'top'
    va_min = 'top' if not invertiere_y else 'bottom'
    
    if abs(y[idx_max]) > 1e-3:
        ax.text(x[idx_max], y[idx_max], f" {y[idx_max]:+.1f}", color=farbe, ha='left', va=va_max, fontweight='bold', fontsize=11)
    if abs(y[idx_min]) > 1e-3:
        ax.text(x[idx_min], y[idx_min], f" {y[idx_min]:+.1f}", color=farbe, ha='left', va=va_min, fontweight='bold', fontsize=11)
    
    max_val = max(abs(np.max(y)), abs(np.min(y)))
    puffer = max_val * 0.3 if max_val > 0 else 1.0
    ax.set_ylim(-max_val - puffer, max_val + puffer)
    
    if invertiere_y:
        ax.invert_yaxis()

# ==============================================================================
# STREAMLIT APP LOGIC
# ==============================================================================
def generiere_pruefungsbeispiel():
    # Optional: Set the page width to wide for better chart viewing
    st.set_page_config(page_title="Baustatik Generator", layout="wide")
    
    st.title("Zufallsgenerator für Baustatik")
    st.write("Klicken Sie auf den Button, um ein neues, stabiles System mit Schnittgrößen zu generieren.")

    if st.button("Neues Beispiel generieren", type="primary"):
        with st.spinner("Berechne FEM..."):
            L, fixed, pinned, rollers, hinges, F_val, F_pos, q_val, q_start, q_end, sys_info = generiere_stabiles_zufallssystem()
            
            x, V_F, M_F, w_F          = berechne_fem(L, fixed, pinned, rollers, hinges, F_val, F_pos, 0, 0, 0)
            _, V_q, M_q, w_q          = berechne_fem(L, fixed, pinned, rollers, hinges, 0, 0, q_val, q_start, q_end)
            _, V_comb, M_comb, w_comb = berechne_fem(L, fixed, pinned, rollers, hinges, F_val, F_pos, q_val, q_start, q_end)

            fig, axs = plt.subplots(4, 3, figsize=(18, 12), sharex='col', facecolor='white')
            fig.subplots_adjust(hspace=0.2, wspace=0.15, left=0.08, right=0.97, top=0.9)
            fig.suptitle(f"{sys_info} | L = {L}m | F = {F_val} kN, q = {q_val} kN/m", fontsize=18, fontweight='bold')

            titles = ["Lastfall 1: Einzelkraft (F)", "Lastfall 2: Gleichlast (q)", "Kombiniert (F + q)"]
            for j in range(3): axs[0, j].set_title(titles[j], fontsize=14, fontweight='bold', pad=15)

            row_labels = ["System", "Querkraft V\n[kN]", "Moment M\n[kNm]", "Biegelinie w\n[mm]"]
            for i in range(4): axs[i, 0].set_ylabel(row_labels[i], fontsize=12, fontweight='bold', labelpad=15)

            zeichne_schaltbild(axs[0, 0], L, fixed, pinned, rollers, hinges, F_val, F_pos, 0, 0, 0)
            zeichne_schaltbild(axs[0, 1], L, fixed, pinned, rollers, hinges, 0, 0, q_val, q_start, q_end)
            zeichne_schaltbild(axs[0, 2], L, fixed, pinned, rollers, hinges, F_val, F_pos, q_val, q_start, q_end)

            for j, (v, m, w) in enumerate(zip([V_F, V_q, V_comb], [M_F, M_q, M_comb], [w_F, w_q, w_comb])):
                plot_verlauf(axs[1, j], x, v, 'dodgerblue', invertiere_y=KONVENTION['V_positiv_nach_unten'])
                plot_verlauf(axs[2, j], x, m, 'crimson', invertiere_y=KONVENTION['M_positiv_nach_unten'])
                plot_verlauf(axs[3, j], x, w, 'forestgreen', invertiere_y=KONVENTION['w_positiv_nach_unten'])

            for j in range(3):
                axs[3, j].set_xlabel("Trägerlänge x [m]", fontweight='bold')
                axs[3, j].tick_params(labelbottom=True)
                axs[3, j].set_xticks(np.arange(0, L + 1, 1))

            st.pyplot(fig)

if __name__ == "__main__":
    generiere_pruefungsbeispiel()
