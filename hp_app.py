import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from CoolProp.CoolProp import PropsSI
from tespy.networks import Network
from tespy.components import Compressor, Valve, HeatExchangerSimple, CycleCloser
from tespy.connections import Connection
from tespy.tools import CharLine

# Streamlit app title
st.title("Heat Pump Heat and Mass Balance Calculator with T-H Diagram")

# User inputs
fluid = st.selectbox("Natural Refrigerant", ["Ammonia", "Propane"])  # Limited to subcritical natural fluids for simplicity
T_evap_C = st.number_input("Evaporator Saturation Temperature (°C)", value=-10.0)
T_cond_C = st.number_input("Condenser Saturation Temperature (°C)", value=40.0)
superheat_K = st.number_input("Superheat (K)", value=5.0)
subcool_K = st.number_input("Subcooling (K)", value=0.0)
eta_s_comp = st.number_input("Compressor Isentropic Efficiency", value=0.8, min_value=0.0, max_value=1.0)
mass_flow = st.number_input("Mass Flow Rate (kg/s)", value=1.0)

# Calculate saturation pressures using CoolProp (in bar)
T_evap_K = T_evap_C + 273.15
T_cond_K = T_cond_C + 273.15
P_evap_bar = PropsSI('P', 'T', T_evap_K, 'Q', 0, fluid) / 1e5
P_cond_bar = PropsSI('P', 'T', T_cond_K, 'Q', 0, fluid) / 1e5

# Set up TESPy network with specified units
nw = Network(
    fluids=[fluid],
    T_unit="C",
    p_unit="bar",
    h_unit="kj / kg",
    m_unit="kg / s"
)

# Components
comp = Compressor("Compressor")
cond = HeatExchangerSimple("Condenser")
val = Valve("Expansion Valve")
eva = HeatExchangerSimple("Evaporator")
cc = CycleCloser("Cycle Closer")

# Connections
c1 = Connection(eva, "out1", cc, "in1", label="1 (Evaporator Outlet)")
c2 = Connection(cc, "out1", comp, "in1", label="2 (Compressor Inlet)")
c3 = Connection(comp, "out1", cond, "in1", label="3 (Condenser Inlet)")
c4 = Connection(cond, "out1", val, "in1", label="4 (Expansion Valve Inlet)")
c5 = Connection(val, "out1", eva, "in1", label="5 (Evaporator Inlet)")

nw.add_conns(c1, c2, c3, c4, c5)

# Set parameters
comp.set_attr(eta_s=eta_s_comp)
cond.set_attr(pr=1.0)
eva.set_attr(pr=1.0)

# Set states
c1.set_attr(fluid={fluid: 1.0}, p=P_evap_bar, T=T_evap_C + superheat_K, m=mass_flow)
c3.set_attr(p=P_cond_bar)
c4.set_attr(T=T_cond_C - subcool_K)

# Bus for compressor power
motor = nw.add_busses(CharLine("Motor"))
motor.add_comps({"comp": comp, "char": -1, "base": "bus"})  # Power input to compressor

# Solve the network
try:
    nw.solve(mode="design")
    nw.print_results()
except ValueError as e:
    st.error(f"Simulation failed: {e}. Adjust inputs (e.g., ensure subcritical conditions).")
    st.stop()

# Extract properties for points (enthalpy in kJ/kg, temperature in °C)
h1 = c1.h.val
T1 = c1.T.val
h2 = c3.h.val
T2 = c3.T.val
h3 = c4.h.val
T3 = c4.T.val
h4 = c5.h.val
T4 = c5.T.val

# Calculate heat and mass balance
q_evap_specific = h1 - h4  # kJ/kg
q_cond_specific = h2 - h3  # kJ/kg (positive for rejected heat)
w_comp_specific = h2 - h1  # kJ/kg

q_evap_total = mass_flow * q_evap_specific  # kW
q_cond_total = mass_flow * q_cond_specific  # kW (rejected)
w_comp_total = mass_flow * w_comp_specific  # kW

cop_heating = abs(q_cond_total) / w_comp_total if w_comp_total != 0 else 0

# Display results
st.subheader("Heat and Mass Balance Results")
st.write(f"Evaporator Heat Absorption: {q_evap_total:.2f} kW ({q_evap_specific:.2f} kJ/kg)")
st.write(f"Condenser Heat Rejection: {q_cond_total:.2f} kW ({q_cond_specific:.2f} kJ/kg)")
st.write(f"Compressor Work Input: {w_comp_total:.2f} kW ({w_comp_specific:.2f} kJ/kg)")
st.write(f"Heating COP: {cop_heating:.2f}")

st.subheader("Cycle Point Properties")
data = {
    "Point": ["1 (Evap Out)", "2 (Comp Out)", "3 (Cond Out)", "4 (Exp Out)"],
    "Temperature (°C)": [T1, T2, T3, T4],
    "Enthalpy (kJ/kg)": [h1, h2, h3, h4],
    "Pressure (bar)": [c1.p.val, c3.p.val, c4.p.val, c5.p.val]
}
st.table(data)

# Generate T-H diagram
st.subheader("T-H Diagram")

# Saturation curve using CoolProp
T_min = PropsSI("TMIN", fluid) + 1
T_crit = PropsSI("TCRIT", fluid) - 1
Tsat_K = np.linspace(max(T_min, T_evap_K - 50), min(T_crit, T_cond_K + 50), 100)
h_liq = [PropsSI("H", "T", t, "Q", 0, fluid) / 1000 for t in Tsat_K]
h_vap = [PropsSI("H", "T", t, "Q", 1, fluid) / 1000 for t in Tsat_K]
Tsat_C = [t - 273.15 for t in Tsat_K]

# Plot
fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(h_liq, Tsat_C, "k-", label="Saturation Liquid")
ax.plot(h_vap, Tsat_C, "k-", label="Saturation Vapor")

# Cycle processes
ax.plot([h4, h1], [T4, T1], "b-", label="Evaporation")
ax.plot([h1, h2], [T1, T2], "r-", label="Compression")
ax.plot([h2, h3], [T2, T3], "g-", label="Condensation")
ax.plot([h3, h4], [T3, T4], "m-", label="Expansion")

# Point markers
ax.plot(h1, T1, "bo", label="Point 1")
ax.plot(h2, T2, "ro", label="Point 2")
ax.plot(h3, T3, "go", label="Point 3")
ax.plot(h4, T4, "mo", label="Point 4")

ax.set_xlabel("Enthalpy (kJ/kg)")
ax.set_ylabel("Temperature (°C)")
ax.set_title(f"T-H Diagram for {fluid} Heat Pump Cycle")
ax.legend()
ax.grid(True)

st.pyplot(fig)
