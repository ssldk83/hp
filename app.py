# app.py — Streamlit Heat Pump (TESPy) with built-in compressor maps (no Excel needed)
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
import numpy as np
import pandas as pd
import streamlit as st

from tespy.networks import Network
from tespy.components import (
    Condenser, CycleCloser, SimpleHeatExchanger, Pump, Sink, Source,
    Valve, Drum, HeatExchanger, Compressor, Splitter, Merge
)
from tespy.connections import Connection
from tespy.tools.characteristics import CharLine
from tespy.tools.characteristics import load_default_char as ldc
from CoolProp.CoolProp import PropsSI as PSI

# ===========================
# 1) Built-in compressor maps
# ===========================
# Paste the real arrays from "SOLID_Compressor data_SSL.xlsm".
# Each map MUST provide "PR" and "ETA_S". Optional "MDOT".
# Units:
#   - PR: absolute pressure ratio (p_out/p_in)
#   - ETA_S: isentropic efficiency (0..1)
#   - MDOT: kg/s (optional; only used as a hint, not a hard constraint)
BUILTIN_COMPRESSOR_MAPS: Dict[str, Dict[str, list]] = {
    # ---> REPLACE THESE PLACEHOLDERS WITH YOUR REAL DATA <---
    "Solid_Default": {
        "PR":    [1.2, 1.5, 2.0, 2.5, 3.0, 3.5],       # example values
        "ETA_S": [0.68, 0.73, 0.78, 0.80, 0.79, 0.76], # example values
        # "MDOT": [0.15, 0.16, 0.17, 0.165, 0.155, 0.14],  # optional
    },
    # Example second curve if you have speed variants:
    "Solid_50Hz": {
        "PR":    [1.2, 1.6, 2.1, 2.6, 3.1],
        "ETA_S": [0.65, 0.72, 0.77, 0.79, 0.78],
    },
}

def _interp(x, xp, fp):
    x = np.clip(x, np.min(xp), np.max(xp))
    return float(np.interp(x, xp, fp))

class StaticCompressorMap:
    """Simple PR→ηs (and optional PR→mdot) interpolator using built-in arrays."""
    def __init__(self, pr_vals, eta_vals, mdot_vals=None):
        self.pr_vals = np.array(pr_vals, dtype=float)
        self.eta_vals = np.array(eta_vals, dtype=float)
        self.mdot_vals = None if mdot_vals is None else np.array(mdot_vals, dtype=float)

    @classmethod
    def from_name(cls, name: str) -> "StaticCompressorMap":
        if name not in BUILTIN_COMPRESSOR_MAPS:
            raise ValueError(f"Unknown compressor map '{name}'")
        data = BUILTIN_COMPRESSOR_MAPS[name]
        if "PR" not in data or "ETA_S" not in data:
            raise ValueError(f"Map '{name}' must define PR and ETA_S arrays.")
        pr = np.array(data["PR"], dtype=float)
        eta = np.array(data["ETA_S"], dtype=float)
        sort_idx = np.argsort(pr)
        pr = pr[sort_idx]
        eta = eta[sort_idx]
        mdot = None
        if "MDOT" in data and data["MDOT"] is not None:
            md = np.array(data["MDOT"], dtype=float)[sort_idx]
            mdot = md
        return cls(pr, eta, mdot)

    def eta_s(self, pr: float, default_eta: float) -> float:
        return _interp(pr, self.pr_vals, self.eta_vals) if len(self.pr_vals) else default_eta

    def mdot_hint(self, pr: float, default_mdot: Optional[float]) -> Optional[float]:
        if self.mdot_vals is None or len(self.pr_vals) == 0:
            return default_mdot
        return _interp(pr, self.pr_vals, self.mdot_vals)

# ===========================
# 2) TESPy model
# ===========================
def c_to_k(t_c: float) -> float:
    return t_c + 273.15

@dataclass
class HPInputs:
    working_fluid: str
    T_source_in: float
    T_source_out: float
    T_sink_in: float
    T_sink_out: float
    duty_kW: float
    ttd_su: float
    ttd_ev: float
    pr_hex: float
    eta_pump: float
    eta_s_default: float
    two_stage: bool
    map_name: Optional[str]  # which built-in map to use (or None)

@dataclass
class HPResults:
    cop: Optional[float]
    q_out_kW: float
    w_comp_kW: float
    w_pumps_kW: float
    table_components: pd.DataFrame
    table_connections: pd.DataFrame
    states: Dict[str, Dict[str, float]]

class HeatPumpTESPy:
    def __init__(self, hp_in: HPInputs):
        self.inp = hp_in
        self.cmap = StaticCompressorMap.from_name(hp_in.map_name) if hp_in.map_name else None

    def _estimate_p_cond(self, T_cond_out_C: float) -> float:
        return PSI("P", "Q", 1, "T", c_to_k(T_cond_out_C), self.inp.working_fluid) / 1e5

    def run(self) -> HPResults:
        nw = Network(T_unit="C", p_unit="bar", h_unit="kJ / kg", m_unit="kg / s")
        wf = self.inp.working_fluid

        # --- Consumer loop ---
        c_in = Source("refrigerant in")
        cons_closer = CycleCloser("consumer cycle closer")
        cd = Condenser("condenser")
        rp = Pump("recirculation pump")
        cons = SimpleHeatExchanger("consumer")
        va_sink = Sink("valve (dummy sink)")

        c0 = Connection(c_in, "out1", cd, "in1", label="0")
        c1 = Connection(cd, "out1", va_sink, "in1", label="1")
        c20 = Connection(cons_closer, "out1", rp, "in1", label="20")
        c21 = Connection(rp, "out1", cd, "in2", label="21")
        c22 = Connection(cd, "out2", cons, "in1", label="22")
        c23 = Connection(cons, "out1", cons_closer, "in1", label="23")
        nw.add_conns(c0, c1, c20, c21, c22, c23)

        cd.set_attr(pr1=self.inp.pr_hex, pr2=self.inp.pr_hex)
        rp.set_attr(eta_s=self.inp.eta_pump)
        cons.set_attr(pr=self.inp.pr_hex)

        p_cond_guess = self._estimate_p_cond(self.inp.T_sink_out)
        c0.set_attr(T=max(self.inp.T_sink_out + 60, 50), p=p_cond_guess, fluid={wf: 1})
        c20.set_attr(T=self.inp.T_sink_in, p=2.0, fluid={"water": 1})
        c22.set_attr(T=self.inp.T_sink_out)
        cons.set_attr(Q=-abs(self.inp.duty_kW) * 1e3)
        nw.solve("design")

        # --- Evaporator & superheater ---
        amb_in = Source("source ambient")
        amb_out = Sink("sink ambient")
        va = Valve("valve")
        dr = Drum("drum")
        ev = HeatExchanger("evaporator")
        su = HeatExchanger("superheater")
        cp1_sink = Sink("cp1 dummy sink")

        nw.del_conns(c1)
        c1 = Connection(cd, "out1", va, "in1", label="1")
        c2 = Connection(va, "out1", dr, "in1", label="2")
        c3 = Connection(dr, "out1", ev, "in2", label="3")
        c4 = Connection(ev, "out2", dr, "in2", label="4")
        c5 = Connection(dr, "out2", su, "in2", label="5")
        c6 = Connection(su, "out2", cp1_sink, "in1", label="6")
        nw.add_conns(c1, c2, c3, c4, c5, c6)

        c17 = Connection(amb_in, "out1", su, "in1", label="17")
        c18 = Connection(su, "out1", ev, "in1", label="18")
        c19 = Connection(ev, "out1", amb_out, "in1", label="19")
        nw.add_conns(c17, c18, c19)

        ev.set_attr(pr1=self.inp.pr_hex)
        su.set_attr(pr1=self.inp.pr_hex, pr2=self.inp.pr_hex)

        c4.set_attr(x=0.9, T=self.inp.T_source_out)
        h_sat = PSI("H", "Q", 1, "T", c_to_k(self.inp.T_source_out + self.inp.ttd_su), wf) / 1e3
        c6.set_attr(h=h_sat)
        c17.set_attr(T=self.inp.T_source_in, fluid={"water": 1})
        c19.set_attr(T=self.inp.T_source_out, p=1.013)
        nw.solve("design")

        # --- Compression & intercooling ---
        cp1 = Compressor("compressor 1")
        cp2 = Compressor("compressor 2") if self.inp.two_stage else None
        ic = HeatExchanger("intercooler")
        hsp = Pump("heat source pump")
        sp = Splitter("splitter")
        me = Merge("merge")
        cv = Valve("control valve")
        hs = Source("ambient intake")
        cc = CycleCloser("hp cycle closer")

        nw.del_conns(c0, c6, c17)
        c6 = Connection(su, "out2", cp1, "in1", label="6")
        c7 = Connection(cp1, "out1", ic, "in1", label="7")
        if self.inp.two_stage:
            c8 = Connection(ic, "out1", cp2, "in1", label="8")
            c9 = Connection(cp2, "out1", cc, "in1", label="9")
        else:
            c8 = Connection(ic, "out1", cc, "in1", label="8")
            c9 = c8
        c0 = Connection(cc, "out1", cd, "in1", label="0")

        c11 = Connection(hs, "out1", hsp, "in1", label="11")
        c12 = Connection(hsp, "out1", sp, "in1", label="12")
        c13 = Connection(sp, "out1", ic, "in2", label="13")
        c14 = Connection(ic, "out2", me, "in1", label="14")
        c15 = Connection(sp, "out2", cv, "in1", label="15")
        c16 = Connection(cv, "out1", me, "in2", label="16")
        c17 = Connection(me, "out1", su, "in1", label="17")
        nw.add_conns(c6, c7, c8, c9, c0, c11, c12, c13, c14, c15, c16, c17)

        cp1.set_attr(pr=2.0)  # rough seed; gets refined
        if cp2:
            cp2.set_attr(pr=2.0)
        ic.set_attr(pr1=self.inp.pr_hex, pr2=self.inp.pr_hex)
        hsp.set_attr(eta_s=self.inp.eta_pump)

        p_cond = self._estimate_p_cond(self.inp.T_sink_out)
        c0.set_attr(p=p_cond, fluid={wf: 1})
        su.set_attr(ttd_u=self.inp.ttd_su)
        ev.set_attr(ttd_l=self.inp.ttd_ev)
        cd.set_attr(ttd_u=self.inp.ttd_su)

        # initial design eta_s
        cp1.set_attr(eta_s=self.inp.eta_s_default)
        if cp2:
            cp2.set_attr(eta_s=self.inp.eta_s_default)
        nw.solve("design")

        # offdesign config like typical TESPy pattern
        cp1.set_attr(design=["eta_s"], offdesign=["eta_s_char"])
        if cp2:
            cp2.set_attr(design=["eta_s"], offdesign=["eta_s_char"])
        rp.set_attr(design=["eta_s"], offdesign=["eta_s_char"])
        hsp.set_attr(design=["eta_s"], offdesign=["eta_s_char"])

        cons.set_attr(design=["pr"], offdesign=["zeta"])
        cd.set_attr(design=["pr2", "ttd_u"], offdesign=["zeta2", "kA_char"])

        kA_char1 = ldc("heat exchanger", "kA_char1", "DEFAULT", CharLine)
        kA_char2 = ldc("heat exchanger", "kA_char2", "EVAPORATING FLUID", CharLine)
        ev.set_attr(kA_char1=kA_char1, kA_char2=kA_char2,
                    design=["pr1", "ttd_l"], offdesign=["zeta1", "kA_char"])
        su.set_attr(design=["pr1", "pr2", "ttd_u"], offdesign=["zeta1", "zeta2", "kA_char"])
        ic.set_attr(design=["pr1", "pr2"], offdesign=["zeta1", "zeta2", "kA_char"])
        c14.set_attr(design=["T"])

        # Apply built-in map to update eta_s from actual PR
        def apply_map_eta():
            if not self.cmap:
                return
            # Protect against None values during the first offdesign pass
            if c6.p.val and c7.p.val:
                pr1 = c7.p.val / c6.p.val
                cp1.set_attr(eta_s=self.cmap.eta_s(pr1, self.inp.eta_s_default))
            if self.inp.two_stage and c8.p.val and c9.p.val:
                pr2 = c9.p.val / c8.p.val
                cp2.set_attr(eta_s=self.cmap.eta_s(pr2, self.inp.eta_s_default))

        apply_map_eta()
        nw.solve("offdesign", design_path=None)
        apply_map_eta()
        nw.solve("offdesign", design_path=None)

        # KPIs
        q_out = abs(cons.Q.val) / 1e3
        w_comp = sum([(cp1.P.val or 0.0), (cp2.P.val if self.inp.two_stage else 0.0)]) / 1e3
        w_pumps = sum([(rp.P.val or 0.0), (hsp.P.val or 0.0)]) / 1e3
        w_in = w_comp + w_pumps
        cop = (q_out / w_in) if w_in > 0 else None

        comp_tbl = nw.results.get("components", pd.DataFrame()).copy()
        conn_tbl = nw.results.get("connections", pd.DataFrame()).copy()

        states = {}
        for lbl, conn in [("0", c0), ("1", c1), ("3", c3), ("5", c5), ("6", c6),
                          ("7", c7), ("8", c8), ("9", c9),
                          ("22", c22), ("23", c23), ("17", c17), ("19", c19)]:
            try:
                states[lbl] = {
                    "p_bar": float(conn.p.val) if conn.p.val is not None else None,
                    "T_C": float(conn.T.val) if conn.T.val is not None else None,
                    "h_kJkg": float(conn.h.val) if conn.h.val is not None else None,
                }
            except Exception:
                pass

        return HPResults(
            cop=cop,
            q_out_kW=q_out,
            w_comp_kW=w_comp,
            w_pumps_kW=w_pumps,
            table_components=comp_tbl,
            table_connections=conn_tbl,
            states=states,
        )

# ===========================
# 3) Streamlit UI
# ===========================
st.set_page_config(page_title="HC Heat Pump — No Excel", layout="wide")
st.title("Hydrocarbon Heat Pump — H&MB (no Excel)")

with st.sidebar:
    st.subheader("Inputs")
    working_fluid = st.selectbox("Working fluid", ["R290", "R600a", "NH3"], index=0)
    colA, colB = st.columns(2)
    with colA:
        T_source_in = st.number_input("Source in (°C)", value=15.0)
        T_sink_in   = st.number_input("Sink in (°C)", value=60.0)
        ttd_su      = st.number_input("Condenser TTD upper (°C)", value=5.0, min_value=1.0)
        eta_s_default = st.number_input("Compressor ηₛ (fallback)", value=0.80, min_value=0.4, max_value=0.95, step=0.01)
    with colB:
        T_source_out = st.number_input("Source out (°C)", value=9.0)
        T_sink_out   = st.number_input("Sink out (°C)", value=90.0)
        ttd_ev       = st.number_input("Evaporator TTD lower (°C)", value=5.0, min_value=1.0)
        pr_hex       = st.number_input("HEX pressure ratio (each side)", value=0.99, min_value=0.9, max_value=1.0, step=0.001)

    duty_kW   = st.number_input("Heat duty to sink (kW)", value=230.0, min_value=1.0)
    eta_pump  = st.number_input("Pump ηₛ", value=0.75, min_value=0.4, max_value=0.95, step=0.01)
    two_stage = st.toggle("Cascade / Two-stage compression", value=True)

    st.markdown("---")
    st.subheader("Compressor Map (built-in)")
    map_name = st.selectbox("Choose map", list(BUILTIN_COMPRESSOR_MAPS.keys()) + ["<None>"], index=0)
    map_name = None if map_name == "<None>" else map_name

tab_run, tab_states, tab_help = st.tabs(["Run", "States/Results", "Map Help"])

with tab_run:
    if st.button("Run Simulation", type="primary"):
        hp_in = HPInputs(
            working_fluid=working_fluid,
            T_source_in=T_source_in,
            T_source_out=T_source_out,
            T_sink_in=T_sink_in,
            T_sink_out=T_sink_out,
            duty_kW=duty_kW,
            ttd_su=ttd_su,
            ttd_ev=ttd_ev,
            pr_hex=pr_hex,
            eta_pump=eta_pump,
            eta_s_default=eta_s_default,
            two_stage=two_stage,
            map_name=map_name,
        )
        try:
            model = HeatPumpTESPy(hp_in)
            res = model.run()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("COP", f"{res.cop:.3f}" if res.cop else "—")
            c2.metric("Q̇ to sink (kW)", f"{res.q_out_kW:.2f}")
            c3.metric("Ẇ compressors (kW)", f"{res.w_comp_kW:.2f}")
            c4.metric("Ẇ pumps (kW)", f"{res.w_pumps_kW:.2f}")

            st.success("Simulation complete.")
            st.session_state["hp_results"] = res
        except Exception as e:
            st.error(f"Simulation failed: {e}")

with tab_states:
    res: Optional[HPResults] = st.session_state.get("hp_results")
    if not res:
        st.info("Run a simulation first.")
    else:
        st.subheader("Key State Points")
        st.dataframe(pd.DataFrame(res.states).T, use_container_width=True)

        st.subheader("Components Table")
        if not res.table_components.empty:
            st.dataframe(res.table_components, use_container_width=True, height=320)
        else:
            st.caption("No component table available.")

        st.subheader("Connections Table")
        if not res.table_connections.empty:
            st.dataframe(res.table_connections, use_container_width=True, height=320)
        else:
            st.caption("No connection table available.")

with tab_help:
    st.markdown("""
**How to embed your Excel data (once):**
1. Open `SOLID_Compressor data_SSL.xlsm`.
2. Identify the columns for **Pressure Ratio (PR)** and **Isentropic Efficiency (ηₛ)** (and optionally **mass flow**).
3. Copy those columns into Python lists and paste them into `BUILTIN_COMPRESSOR_MAPS`.
4. Select your map name in the sidebar. Done—no Excel needed at runtime.

If you send me a screenshot or the column names + values, I’ll hard‑code the exact arrays for you.
""")
