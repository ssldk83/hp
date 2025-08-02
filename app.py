# app.py

import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
from simulation import run_simulation

# --- Streamlit UI ---
st.set_page_config(page_title="TESPy Heat Pump", layout="wide")
st.title("TESPy Heat Pump Simulation")

fluid_label = st.selectbox("Select Working Fluid", ["Ammonia (NH₃)", "Propane (R290)", "Isobutane (R600a)"])
fluid_map = {
    "Ammonia (NH₃)": "NH3",
    "Propane (R290)": "Propane",
    "Isobutane (R600a)": "Isobutane"
}
working_fluid = fluid_map[fluid_label]

# Temperature inputs
st.markdown("### Temperature Settings")
col1, col2 = st.columns(2)
with col1:
    sink_return = st.number_input("District Heating Return Temp [°C]", value=40.0)
    source_in = st.number_input("Wastewater Inlet Temp [°C]", value=10.8)
with col2:
    sink_supply = st.number_input("District Heating Supply Temp [°C]", value=70.0)
    source_out = st.number_input("Wastewater Outlet Temp [°C]", value=5.0)

# Run simulation
with st.spinner("Running TESPy simulation..."):
    cop, results = run_simulation(working_fluid, sink_return, sink_supply, source_in, source_out)

st.success("Simulation completed.")
st.metric("COP", f"{cop:.2f}")

# Show results
for section, data in results.items():
    st.subheader(section.title())
    df = pd.DataFrame.from_dict(data, orient="index")
    st.dataframe(df.style.format(precision=3), use_container_width=True)

# SVG schematic
st.subheader("Heat Pump Schematic")
try:
    with open("hp_sample.svg", "r") as f:
        svg_code = f.read()
    components.html(svg_code, height=600)
except FileNotFoundError:
    st.warning("SVG file not found.")
