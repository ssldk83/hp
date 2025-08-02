import streamlit as st
import numpy as np
import plotly.graph_objects as go
from CoolProp.CoolProp import PropsSI
from tespy.networks import Network
from tespy.components import Compressor, Valve, SimpleHeatExchanger, CycleCloser
from tespy.connections import Connection
from tespy.tools.helpers import TESPyNetworkError

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

# Calculate saturation pressures using CoolProp (in bar)
try:
    T_evap_K = T_evap_C + 273.15
    T_cond_K = T_cond_C + 273.15
    P_evap_bar = PropsSI('P', 'T', T_evap_K, 'Q', 0, fluid) / 1e5
    P_cond_bar = PropsSI('P', 'T', T_cond_K, 'Q', 0, fluid) / 1e5
    
    # Check if conditions are subcritical
    T_crit = PropsSI('TCRIT', fluid)
    if T_cond_K >= T_crit:
        st.error(f"Condenser temperature too high. Critical temperature for {fluid_display} is {T_crit-273.15:.1f}°C")
        st.stop()
        
except Exception as e:
    st.error(f"Error calculating fluid properties: {e}")
    st.stop()

# Set up TESPy network with correct units
nw = Network(
    fluids=[fluid],
    T_unit="C",
    p_unit="bar",
    h_unit="kJ/kg",
    m_unit="kg/s"
)

# Components
comp = Compressor("Compressor")
cond = SimpleHeatExchanger("Condenser")
val = Valve("Expansion Valve")
eva = SimpleHeatExchanger("Evaporator")
cc = CycleCloser("Cycle Closer")

# Connections
c1 = Connection(eva, "out1", cc, "in1", label="1")
c2 = Connection(cc, "out1", comp, "in1", label="2")
c3 = Connection(comp, "out1", cond, "in1", label="3")
c4 = Connection(cond, "out1", val, "in1", label="4")
c5 = Connection(val, "out1", eva, "in1", label="5")

nw.add_conns(c1, c2, c3, c4, c5)

# Set component parameters
comp.set_attr(eta_s=eta_s_comp)
cond.set_attr(pr=1.0)  # Pressure ratio (no pressure drop)
eva.set_attr(pr=1.0)   # Pressure ratio (no pressure drop)

# Set connection states
c1.set_attr(fluid={fluid: 1.0}, p=P_evap_bar, T=T_evap_C + superheat_K, m=mass_flow)
c3.set_attr(p=P_cond_bar)
c4.set_attr(T=T_cond_C - subcool_K)

# Solve the network
try:
    nw.solve(mode="design")
    st.success("Simulation converged successfully!")
except Exception as e:
    st.error(f"Simulation failed: {e}")
    st.error("Try adjusting the input parameters (temperatures, superheat, subcooling)")
    st.stop()

# Extract properties for points
h1 = c1.h.val  # kJ/kg
T1 = c1.T.val  # °C
p1 = c1.p.val  # bar

h2 = c2.h.val  # kJ/kg
T2 = c2.T.val  # °C
p2 = c2.p.val  # bar

h3 = c3.h.val  # kJ/kg
T3 = c3.T.val  # °C
p3 = c3.p.val  # bar

h4 = c4.h.val  # kJ/kg
T4 = c4.T.val  # °C
p4 = c4.p.val  # bar

# Calculate heat and mass balance
q_evap_specific = h1 - h4  # kJ/kg (heat absorbed)
q_cond_specific = h2 - h3  # kJ/kg (heat rejected)
w_comp_specific = h2 - h1  # kJ/kg (work input)

q_evap_total = mass_flow * q_evap_specific  # kW
q_cond_total = mass_flow * q_cond_specific  # kW
w_comp_total = mass_flow * w_comp_specific  # kW

cop_heating = q_cond_total / w_comp_total if w_comp_total > 0 else 0
cop_cooling = q_evap_total / w_comp_total if w_comp_total > 0 else 0

# Energy balance check
energy_balance = q_evap_total + w_comp_total - q_cond_total

# Display results
st.subheader("Heat and Mass Balance Results")
col1, col2 = st.columns(2)

with col1:
    st.write(f"**Evaporator Heat Absorption:** {q_evap_total:.2f} kW")
    st.write(f"**Condenser Heat Rejection:** {q_cond_total:.2f} kW")
    st.write(f"**Compressor Work Input:** {w_comp_total:.2f} kW")

with col2:
    st.write(f"**Heating COP:** {cop_heating:.2f}")
    st.write(f"**Cooling COP:** {cop_cooling:.2f}")
    st.write(f"**Energy Balance Error:** {energy_balance:.3f} kW")

st.subheader("Cycle Point Properties")
data = {
    "Point": ["1 (Evap Out)", "2 (Comp Out)", "3 (Cond Out)", "4 (Exp Val Out)"],
    "Temperature (°C)": [f"{T1:.1f}", f"{T2:.1f}", f"{T3:.1f}", f"{T4:.1f}"],
    "Pressure (bar)": [f"{p1:.2f}", f"{p2:.2f}", f"{p3:.2f}", f"{p4:.2f}"],
    "Enthalpy (kJ/kg)": [f"{h1:.1f}", f"{h2:.1f}", f"{h3:.1f}", f"{h4:.1f}"]
}
st.table(data)

# Generate T-H diagram
st.subheader("T-H Diagram")

try:
    # Saturation curve using CoolProp
    T_min = max(PropsSI("TMIN", fluid) + 5, T_evap_K - 50)  # Add safety margin
    T_crit = PropsSI("TCRIT", fluid) - 5  # Subtract safety margin
    T_max = min(T_crit, T_cond_K + 50)
    
    Tsat_K = np.linspace(T_min, T_max, 100)
    h_liq = []
    h_vap = []
    Tsat_C = []
    
    for t in Tsat_K:
        try:
            h_l = PropsSI("H", "T", t, "Q", 0, fluid) / 1000  # Convert to kJ/kg
            h_v = PropsSI("H", "T", t, "Q", 1, fluid) / 1000  # Convert to kJ/kg
            h_liq.append(h_l)
            h_vap.append(h_v)
            Tsat_C.append(t - 273.15)
        except:
            continue  # Skip problematic points
    
    # Create Plotly figure
    fig = go.Figure()
    
    # Saturation curves
    fig.add_trace(go.Scatter(
        x=h_liq, y=Tsat_C, 
        mode='lines', name='Saturated Liquid', 
        line=dict(color='black', width=2)
    ))
    fig.add_trace(go.Scatter(
        x=h_vap, y=Tsat_C, 
        mode='lines', name='Saturated Vapor', 
        line=dict(color='black', width=2)
    ))
    
    # Cycle processes
    fig.add_trace(go.Scatter(
        x=[h4, h1], y=[T4, T1], 
        mode='lines+markers', name='4→1 Evaporation', 
        line=dict(color='blue', width=3),
        marker=dict(size=8)
    ))
    fig.add_trace(go.Scatter(
        x=[h1, h2], y=[T1, T2], 
        mode='lines+markers', name='1→2 Compression', 
        line=dict(color='red', width=3),
        marker=dict(size=8)
    ))
    fig.add_trace(go.Scatter(
        x=[h2, h3], y=[T2, T3], 
        mode='lines+markers', name='2→3 Condensation', 
        line=dict(color='green', width=3),
        marker=dict(size=8)
    ))
    fig.add_trace(go.Scatter(
        x=[h3, h4], y=[T3, T4], 
        mode='lines+markers', name='3→4 Expansion', 
        line=dict(color='orange', width=3),
        marker=dict(size=8)
    ))
    
    # Point labels
    fig.add_annotation(x=h1, y=T1, text="1", showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2)
    fig.add_annotation(x=h2, y=T2, text="2", showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2)
    fig.add_annotation(x=h3, y=T3, text="3", showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2)
    fig.add_annotation(x=h4, y=T4, text="4", showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=2)
    
    # Layout
    fig.update_layout(
        title=f"T-H Diagram for {fluid_display} Heat Pump Cycle",
        xaxis_title="Enthalpy (kJ/kg)",
        yaxis_title="Temperature (°C)",
        showlegend=True,
        width=800,
        height=600,
        xaxis=dict(showgrid=True, gridwidth=1, gridcolor='lightgray'),
        yaxis=dict(showgrid=True, gridwidth=1, gridcolor='lightgray'),
        template="plotly_white"
    )
    
    # Display plot
    st.plotly_chart(fig, use_container_width=True)
    
except Exception as e:
    st.error(f"Error generating T-H diagram: {e}")

# Additional information
st.subheader("System Information")
st.write(f"**Working Fluid:** {fluid_display} ({fluid})")
st.write(f"**Pressure Ratio:** {p2/p1:.2f}")
st.write(f"**Temperature Lift:** {T2-T1:.1f} K")

# Performance metrics
st.subheader("Performance Metrics")
carnot_cop = T_cond_K / (T_cond_K - T_evap_K)
carnot_efficiency = cop_heating / carnot_cop if carnot_cop > 0 else 0

st.write(f"**Carnot COP (Heating):** {carnot_cop:.2f}")
st.write(f"**Second Law Efficiency:** {carnot_efficiency:.1%}")
