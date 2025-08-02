import streamlit as st
import numpy as np
import plotly.graph_objects as go
from CoolProp.CoolProp import PropsSI
from tespy.networks import Network
from tespy.components import Compressor, Valve, SimpleHeatExchanger, CycleCloser
from tespy.connections import Connection

# Streamlit app title
st.title("Heat Pump Heat and Mass Balance Calculator with T-H Diagram")

# User inputs
fluid_map = {"Ammonia": "NH3", "Propane": "Propane"}
fluid_display = st.selectbox("Natural Refrigerant", ["Ammonia", "Propane"])
fluid = fluid_map[fluid_display]

T_evap_C = st.number_input("Evaporator Saturation Temperature (°C)", value=-10.0)
T_cond_C = st.number_input("Condenser Saturation Temperature (°C)", value=40.0)
superheat_K = st.number_input("Superheat (K)", value=5.0)
subcool_K = st.number_input("Subcooling (K)", value=0.0)
eta_s_comp = st.number_input("Compressor Isentropic Efficiency", value=0.8, min_value=0.0, max_value=1.0)
mass_flow = st.number_input("Mass Flow Rate (kg/s)", value=1.0)

# Validate inputs
if T_evap_C >= T_cond_C:
    st.error("Evaporator temperature must be lower than condenser temperature.")
    st.stop()

# Calculate saturation pressures (bar)
T_evap_K = T_evap_C + 273.15
T_cond_K = T_cond_C + 273.15

try:
    P_evap_bar = PropsSI('P', 'T', T_evap_K, 'Q', 0, fluid) / 1e5
    P_cond_bar = PropsSI('P', 'T', T_cond_K, 'Q', 0, fluid) / 1e5

    T_crit = PropsSI('TCRIT', fluid)
    if T_cond_K >= T_crit:
        st.error(f"Condenser temperature too high. Critical temperature for {fluid_display} is {T_crit - 273.15:.1f}°C")
        st.stop()
except Exception as e:
    st.error(f"Error calculating fluid properties: {e}")
    st.stop()

# TESPy network setup
nw = Network(fluids=[fluid], T_unit='C', p_unit='bar', h_unit='kJ / kg', m_unit='kg / s')

# Components
comp = Compressor('compressor')
cond = SimpleHeatExchanger('condenser')
val = Valve('expansion_valve')
eva = SimpleHeatExchanger('evaporator')
cc = CycleCloser('cycle_closer')

# Connections
c1 = Connection(eva, 'out1', cc, 'in1')
c2 = Connection(cc, 'out1', comp, 'in1')
c3 = Connection(comp, 'out1', cond, 'in1')
c4 = Connection(cond, 'out1', val, 'in1')
c5 = Connection(val, 'out1', eva, 'in1')
nw.add_conns(c1, c2, c3, c4, c5)

# Set parameters
comp.set_attr(eta_s=eta_s_comp)
cond.set_attr(pr=1)
eva.set_attr(pr=1)

c1.set_attr(fluid={fluid: 1}, p=P_evap_bar, T=T_evap_C + superheat_K, m=mass_flow)
c3.set_attr(p=P_cond_bar)
c4.set_attr(T=T_cond_C - subcool_K)

# Solve network
try:
    nw.solve('design')
    nw.print_results()
    st.success("Simulation converged successfully!")
except Exception as e:
    st.error(f"Simulation failed: {e}")
    st.stop()

# Retrieve results
h = [conn.h.val for conn in [c1, c2, c3, c4]]
T = [conn.T.val for conn in [c1, c2, c3, c4]]
p = [conn.p.val for conn in [c1, c2, c3, c4]]

# Heat balance
q_evap = mass_flow * (h[0] - h[3])
q_cond = mass_flow * (h[1] - h[2])
w_comp = mass_flow * (h[1] - h[0])

cop_heat = q_cond / w_comp
cop_cool = q_evap / w_comp

# Display results
st.subheader("Heat and Mass Balance Results")
st.write(f"Evaporator Heat: {q_evap:.2f} kW")
st.write(f"Condenser Heat: {q_cond:.2f} kW")
st.write(f"Compressor Work: {w_comp:.2f} kW")
st.write(f"Heating COP: {cop_heat:.2f}")
st.write(f"Cooling COP: {cop_cool:.2f}")

# T-H Diagram
Ts = np.linspace(T_evap_K - 30, T_cond_K + 30, 100)
h_l = [PropsSI('H', 'T', T, 'Q', 0, fluid) / 1e3 for T in Ts]
h_v = [PropsSI('H', 'T', T, 'Q', 1, fluid) / 1e3 for T in Ts]

fig = go.Figure()
fig.add_trace(go.Scatter(x=h_l, y=Ts - 273.15, mode='lines', name='Saturated Liquid'))
fig.add_trace(go.Scatter(x=h_v, y=Ts - 273.15, mode='lines', name='Saturated Vapor'))
fig.add_trace(go.Scatter(x=h + [h[0]], y=[t - 273.15 for t in T] + [T[0] - 273.15], mode='lines+markers', name='Cycle'))

fig.update_layout(title="T-H Diagram", xaxis_title="Enthalpy (kJ/kg)", yaxis_title="Temperature (°C)", template='plotly_white')
st.plotly_chart(fig, use_container_width=True)
