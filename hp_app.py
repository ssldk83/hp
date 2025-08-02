import streamlit as st
import numpy as np
import plotly.graph_objects as go
from CoolProp.CoolProp import PropsSI

st.set_page_config(page_title="T-H Diagram for Heat Pump", layout="centered")

st.title("T-H Diagram for Heat Pump Cycle")

# --- Fluid selection and defaults ---
fluid_options = {
    "Propane": {
        "fluid": "Propane",
        "Tevap": -10,
        "Tcond": 40,
        "superheat": 5,
        "subcool": 5
    },
    "Isobutane": {
        "fluid": "Isobutane",
        "Tevap": 0,
        "Tcond": 50,
        "superheat": 7,
        "subcool": 7
    }
}

fluid_name = st.selectbox("Select Working Fluid:", list(fluid_options.keys()))
fluid_config = fluid_options[fluid_name]
fluid = fluid_config["fluid"]

st.markdown("### Cycle Conditions (°C / K)")

col1, col2 = st.columns(2)
with col1:
    Tevap_C = st.number_input("Evaporation Temperature [°C]", value=fluid_config["Tevap"])
    superheat_K = st.number_input("Superheat [K]", value=fluid_config["superheat"])
with col2:
    Tcond_C = st.number_input("Condensation Temperature [°C]", value=fluid_config["Tcond"])
    subcool_K = st.number_input("Subcool [K]", value=fluid_config["subcool"])

# Convert to Kelvin
Tevap_K = Tevap_C + 273.15
Tcond_K = Tcond_C + 273.15

# --- Calculate cycle points ---
points = {}

try:
    # 1: Evaporator outlet (superheated vapor)
    T1 = Tevap_K + superheat_K
    h1 = PropsSI("H", "T", T1, "P", PropsSI("P", "T", Tevap_K, "Q", 1, fluid), fluid)

    # 2: Condenser inlet (same pressure as Tcond, isentropic compression)
    s1 = PropsSI("S", "T", T1, "P", PropsSI("P", "T", Tevap_K, "Q", 1, fluid), fluid)
    p2 = PropsSI("P", "T", Tcond_K, "Q", 1, fluid)
    T2 = PropsSI("T", "P", p2, "S", s1, fluid)
    h2 = PropsSI("H", "P", p2, "S", s1, fluid)

    # 3: Condenser outlet (subcooled liquid)
    T3 = Tcond_K - subcool_K
    h3 = PropsSI("H", "T", T3, "P", p2, fluid)

    # 4: Expansion valve outlet (evaporator inlet, isoenthalpic expansion)
    h4 = h3
    p4 = PropsSI("P", "T", Tevap_K, "Q", 0, fluid)
    T4 = PropsSI("T", "P", p4, "H", h4, fluid)

    points = {
        "1: Evap. outlet (superheated vapor)": (h1/1000, T1 - 273.15),
        "2: Comp. outlet (high pressure vapor)": (h2/1000, T2 - 273.15),
        "3: Cond. outlet (subcooled liquid)": (h3/1000, T3 - 273.15),
        "4: Exp. outlet (saturated mix)": (h4/1000, T4 - 273.15)
    }

except Exception as e:
    st.error(f"Error calculating cycle points: {e}")

# --- Generate saturation curve ---
T_min = PropsSI(fluid, "Tmin") + 1
T_crit = PropsSI(fluid, "Tcrit") - 1
T_vals = np.linspace(T_min, T_crit, 300)
h_liq, h_vap = [], []

for T in T_vals:
    try:
        h_liq.append(PropsSI("H", "T", T, "Q", 0, fluid) / 1000)
        h_vap.append(PropsSI("H", "T", T, "Q", 1, fluid) / 1000)
    except:
        h_liq.append(np.nan)
        h_vap.append(np.nan)

T_vals_C = T_vals - 273.15

# --- Plotting ---
fig = go.Figure()

# Saturation curve
fig.add_trace(go.Scatter(
    x=h_liq, y=T_vals_C, mode='lines', name='Saturated Liquid', line=dict(color='blue')))
fig.add_trace(go.Scatter(
    x=h_vap, y=T_vals_C, mode='lines', name='Saturated Vapor', line=dict(color='red')))

# Cycle points
if points:
    for label, (h, T) in points.items():
        fig.add_trace(go.Scatter(
            x=[h], y=[T], mode='markers+text',
            name=label,
            text=[label],
            textposition="top center",
            marker=dict(size=10)))

    # Connect cycle points
    cycle_coords = list(points.values())
    cycle_coords.append(cycle_coords[0])  # close the loop
    h_cycle, T_cycle = zip(*cycle_coords)
    fig.add_trace(go.Scatter(
        x=h_cycle, y=T_cycle, mode='lines',
        name='Cycle Loop', line=dict(color='black', dash='dash')))

fig.update_layout(
    title=f"T-H Diagram for {fluid_name}",
    xaxis_title="Enthalpy [kJ/kg]",
    yaxis_title="Temperature [°C]",
    height=650
)

st.plotly_chart(fig, use_container_width=True)
