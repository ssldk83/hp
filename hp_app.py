import streamlit as st
import pandas as pd
import uuid
import os
import json
import streamlit.components.v1 as components
from tespy.networks import Network
from tespy.components import (
    Condenser, CycleCloser, SimpleHeatExchanger, Pump, Sink, Source,
    Valve, Drum, HeatExchanger, Compressor, Splitter, Merge
)
from tespy.connections import Connection
from tespy.tools.characteristics import CharLine
from CoolProp.CoolProp import PropsSI
from tempfile import NamedTemporaryFile

def json_with_nan_fix(obj):
    return json.loads(json.dumps(obj, default=lambda x: None))

# Default fluid-specific parameters
fluid_defaults = {
    "NH3": {"cond_T": 95, "inlet_T": 170},
    "Propane": {"cond_T": 50, "inlet_T": 120},
    "Isobutane": {"cond_T": 45, "inlet_T": 110}
}

def run_simulation(working_fluid):
    defaults = fluid_defaults[working_fluid]
    nw = Network(T_unit="C", p_unit="bar", h_unit="kJ / kg", m_unit="kg / s")

    # ------------------ COMPONENTS ------------------
    c_in = Source("refrigerant in")
    cons_closer = CycleCloser("consumer cycle closer")
    va = Sink("valve")
    cd = Condenser("condenser")
    rp = Pump("recirculation pump")
    cons = SimpleHeatExchanger("consumer")

    # ------------------ CONNECTIONS ------------------
    c0 = Connection(c_in, "out1", cd, "in1", label="0")
    c1 = Connection(cd, "out1", va, "in1", label="1")
    c20 = Connection(cons_closer, "out1", rp, "in1", label="20")
    c21 = Connection(rp, "out1", cd, "in2", label="21")
    c22 = Connection(cd, "out2", cons, "in1", label="22")
    c23 = Connection(cons, "out1", cons_closer, "in1", label="23")
    nw.add_conns(c0, c1, c20, c21, c22, c23)

    # ------------------ ATTRIBUTES ------------------
    cd.set_attr(pr1=0.99, pr2=0.99)
    rp.set_attr(eta_s=0.75)
    cons.set_attr(pr=0.99)

    p_cond = PropsSI("P", "Q", 1, "T", 273.15 + defaults["cond_T"], working_fluid) / 1e5
    c0.set_attr(T=defaults["inlet_T"], p=p_cond, fluid={working_fluid: 1})
    c20.set_attr(T=60, p=2, fluid={"water": 1})
    c22.set_attr(T=90)
    cons.set_attr(Q=-230e3)

    nw.solve("design")

    # ------------------ EVAPORATOR SYSTEM ------------------
    amb_in = Source("source ambient")
    amb_out = Sink("sink ambient")
    va = Valve("valve")
    dr = Drum("drum")
    ev = HeatExchanger("evaporator")
    su = HeatExchanger("superheater")
    cp1 = Sink("compressor 1")

    nw.del_conns(c1)
    c1 = Connection(cd, "out1", va, "in1", label="1")
    c2 = Connection(va, "out1", dr, "in1", label="2")
    c3 = Connection(dr, "out1", ev, "in2", label="3")
    c4 = Connection(ev, "out2", dr, "in2", label="4")
    c5 = Connection(dr, "out2", su, "in2", label="5")
    c6 = Connection(su, "out2", cp1, "in1", label="6")
    c17 = Connection(amb_in, "out1", su, "in1", label="17")
    c18 = Connection(su, "out1", ev, "in1", label="18")
    c19 = Connection(ev, "out1", amb_out, "in1", label="19")
    nw.add_conns(c1, c2, c3, c4, c5, c6, c17, c18, c19)

    ev.set_attr(pr1=0.99)
    su.set_attr(pr1=0.99, pr2=0.99)
    c4.set_attr(x=0.9, T=5)
    h_sat = PropsSI("H", "Q", 1, "T", 273.15 + 15, working_fluid) / 1e3
    c6.set_attr(h=h_sat)
    c17.set_attr(T=15, fluid={"water": 1})
    c19.set_attr(T=9, p=1.013)
    nw.solve("design")

    # ------------------ COMPRESSORS + LOOP ------------------
    cp1 = Compressor("compressor 1")
    cp2 = Compressor("compressor 2")
    ic = HeatExchanger("intermittent cooling")
    hsp = Pump("heat source pump")
    sp = Splitter("splitter")
    me = Merge("merge")
    cv = Valve("control valve")
    hs = Source("ambient intake")
    cc = CycleCloser("heat pump cycle closer")

    nw.del_conns(c0, c6, c17)
    c6 = Connection(su, "out2", cp1, "in1", label="6")
    c7 = Connection(cp1, "out1", ic, "in1", label="7")
    c8 = Connection(ic, "out1", cp2, "in1", label="8")
    c9 = Connection(cp2, "out1", cc, "in1", label="9")
    c0 = Connection(cc, "out1", cd, "in1", label="0")
    c11 = Connection(hs, "out1", hsp, "in1", label="11")
    c12 = Connection(hsp, "out1", sp, "in1", label="12")
    c13 = Connection(sp, "out1", ic, "in2", label="13")
    c14 = Connection(ic, "out2", me, "in1", label="14")
    c15 = Connection(sp, "out2", cv, "in1", label="15")
    c16 = Connection(cv, "out1", me, "in2", label="16")
    c17 = Connection(me, "out1", su, "in1", label="17")
    nw.add_conns(c6, c7, c8, c9, c0, c11, c12, c13, c14, c15, c16, c17)

    pr = (c1.p.val / c5.p.val) ** 0.5
    cp1.set_attr(pr=pr)
    ic.set_attr(pr1=0.99, pr2=0.98)
    hsp.set_attr(eta_s=0.75)
    c0.set_attr(p=p_cond, fluid={working_fluid: 1})
    c6.set_attr(h=c5.h.val + 10)
    c8.set_attr(h=c5.h.val + 10)
    c7.set_attr(h=c5.h.val * 1.2)
    c9.set_attr(h=c5.h.val * 1.2)
    c11.set_attr(p=1.013, T=15, fluid={"water": 1})
    c14.set_attr(T=30)
    nw.solve("design")

    # ------------------ FINAL CLEANUP ------------------
    c0.set_attr(p=None)
    cd.set_attr(ttd_u=5)
    c4.set_attr(T=None)
    ev.set_attr(ttd_l=5)
    c6.set_attr(h=None)
    su.set_attr(ttd_u=5)
    c7.set_attr(h=None)
    cp1.set_attr(eta_s=0.8)
    c9.set_attr(h=None)
    cp2.set_attr(eta_s=0.8)
    c8.set_attr(h=None, Td_bp=4)
    nw.solve("design")

    # Design/offdesign flags
    cp1.set_attr(design=["eta_s"], offdesign=["eta_s_char"])
    cp2.set_attr(design=["eta_s"], offdesign=["eta_s_char"])
    rp.set_attr(design=["eta_s"], offdesign=["eta_s_char"])
    hsp.set_attr(design=["eta_s"], offdesign=["eta_s_char"])
    cons.set_attr(design=["pr"], offdesign=["zeta"])
    cd.set_attr(design=["pr2", "ttd_u"], offdesign=["zeta2", "kA_char"])

    # Characteristic lines
    kA_char1 = CharLine([0, 1], [0, 1])
    kA_char2 = CharLine([0, 1], [0, 1])
    ev.set_attr(kA_char1=kA_char1, kA_char2=kA_char2,
                design=["pr1", "ttd_l"], offdesign=["zeta1", "kA_char"])
    su.set_attr(design=["pr1", "pr2", "ttd_u"], offdesign=["zeta1", "zeta2", "kA_char"])
    ic.set_attr(design=["pr1", "pr2"], offdesign=["zeta1", "zeta2", "kA_char"])
    c14.set_attr(design=["T"])

    # Save & offdesign solve
    with NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        design_path = tmp.name
        nw.save(design_path)
    nw.solve("offdesign", design_path=design_path)
    os.remove(design_path)

    q_out = cons.Q.val
    w_in = cp1.P.val + cp2.P.val + rp.P.val + hsp.P.val
    cop = abs(q_out) / w_in if w_in else None
    results = {k: v.to_dict() for k, v in nw.results.items()}
    return cop, results

# ------------------ STREAMLIT UI ------------------
st.set_page_config(page_title="TESPy NH₃ Heat Pump", layout="wide")
st.title("TESPy Heat Pump Simulation")

# --- Sidebar: Working Fluid ---
fluid_label = st.sidebar.selectbox("Working Fluid", {
    "Ammonia (NH₃)": "NH3",
    "Propane (R290)": "Propane",
    "Isobutane (R600a)": "Isobutane"
})

# --- Sidebar: SVG Schematic ---
st.sidebar.markdown("### Heat Pump Schematic")
try:
    with open("hp_sample.svg", "r") as f:
        svg_code = f.read()
    with st.sidebar:
        components.html(svg_code, height=500)
except FileNotFoundError:
    st.sidebar.warning("SVG diagram not found (hp_sample.svg)")

# --- Run Simulation ---
with st.spinner(f"Running simulation for {fluid_label}..."):
    cop, results = run_simulation(fluid_label)

st.success("Simulation completed.")
st.metric(label="Coefficient of Performance (COP)", value=f"{cop:.2f}")

# --- Show Results ---
for section, data in results.items():
    st.subheader(section.title())
    df = pd.DataFrame.from_dict(data, orient="index")
    st.dataframe(df.style.format(precision=3), use_container_width=True)
