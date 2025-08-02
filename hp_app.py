import streamlit as st
import numpy as np
import plotly.graph_objects as go
from CoolProp.CoolProp import PropsSI

# --- Streamlit App ---
st.title("T-H Diagram for Selected Fluid")
st.markdown("Generates a Temperature-Enthalpy (T-H) diagram for saturated liquid and vapor.")

# --- Fluid selection ---
fluid_options = {
    "Propane": "Propane",
    "Isobutane": "Isobutane"
}
fluid_name = st.selectbox("Select Fluid:", list(fluid_options.keys()))
fluid = fluid_options[fluid_name]

# --- Get fluid limits ---
T_min = PropsSI(fluid, "Tmin") + 1  # Avoid numerical instability near min
T_crit = PropsSI(fluid, "Tcrit") - 1  # Avoid numerical instability near critical
T_vals = np.linspace(T_min, T_crit, 200)

# --- Calculate saturation enthalpies ---
h_liq = []
h_vap = []
for T in T_vals:
    try:
        h_l = PropsSI("H", "T", T, "Q", 0, fluid)
        h_v = PropsSI("H", "T", T, "Q", 1, fluid)
        h_liq.append(h_l / 1000)  # convert J/kg to kJ/kg
        h_vap.append(h_v / 1000)
    except:
        h_liq.append(np.nan)
        h_vap.append(np.nan)

T_vals_C = T_vals - 273.15  # Convert to Celsius

# --- Plot ---
fig = go.Figure()
fig.add_trace(go.Scatter(x=h_liq, y=T_vals_C, mode='lines', name='Saturated Liquid'))
fig.add_trace(go.Scatter(x=h_vap, y=T_vals_C, mode='lines', name='Saturated Vapor'))

fig.update_layout(
    title=f"T-H Diagram for {fluid_name}",
    xaxis_title="Enthalpy [kJ/kg]",
    yaxis_title="Temperature [°C]",
    height=600
)

st.plotly_chart(fig, use_container_width=True)
