import streamlit as st
from tespy.networks import Network
from tespy.components import (Source, Sink, CycleCloser, Compressor, Condenser, Valve,
                              Pump, HeatExchanger)
from tespy.connections import Connection
from CoolProp.CoolProp import PropsSI as PSI

# Define the simulation logic in a function
def run_simulation(working_fluid, source_temp_in, source_temp_out, sink_temp_in, sink_temp_out):

    # Setup network
    nw = Network(T_unit='C', p_unit='bar', h_unit='kJ / kg', m_unit='kg / s', fluids=[working_fluid, 'water'])

    # Components
    cc = CycleCloser('cycle closer')
    comp = Compressor('compressor')
    cond = Condenser('condenser')
    valve = Valve('expansion valve')
    evap = HeatExchanger('evaporator')

    source = Source('source inlet')
    source_sink = Sink('source outlet')
    sink = Sink('district heating out')
    sink_source = Source('district heating in')

    # Connections
    c0 = Connection(cc, 'out1', comp, 'in1')
    c1 = Connection(comp, 'out1', cond, 'in1')
    c2 = Connection(cond, 'out1', valve, 'in1')
    c3 = Connection(valve, 'out1', evap, 'in2')
    c4 = Connection(evap, 'out2', cc, 'in1')

    c_source = Connection(source, 'out1', evap, 'in1')
    c_source_sink = Connection(evap, 'out1', source_sink, 'in1')
    c_sink_source = Connection(sink_source, 'out1', cond, 'in2')
    c_sink = Connection(cond, 'out2', sink, 'in1')

    nw.add_conns(c0, c1, c2, c3, c4, c_source, c_source_sink, c_sink_source, c_sink)

    # Set parameters
    c_source.set_attr(T=source_temp_in, fluid={'water': 1})
    c_source_sink.set_attr(T=source_temp_out)

    c_sink_source.set_attr(T=sink_temp_in, fluid={'water': 1})
    c_sink.set_attr(T=sink_temp_out)

    p_cond = PSI('P', 'Q', 1, 'T', sink_temp_out + 273.15, working_fluid) / 1e5
    c1.set_attr(p=p_cond)
    c3.set_attr(p=2)

    evap.set_attr(pr1=0.98, pr2=0.98)
    cond.set_attr(pr1=0.98, pr2=0.98)
    comp.set_attr(eta_s=0.8)

    # Solve network
    nw.solve('design')

    # Compute COP
    q_out = cond.Q.val
    w_in = comp.P.val
    cop = abs(q_out) / w_in if w_in else None

    return nw.results, cop

# Streamlit App
st.title("Heat Pump Heat & Mass Balance Calculator")

fluid_choice = st.selectbox("Select Refrigerant:", ["NH3", "Propane", "Isobutane"])
source_choice = st.selectbox("Select Heat Source:", ["Wastewater", "Air", "Datacenter"])

col1, col2 = st.columns(2)
with col1:
    source_temp_in = st.number_input("Source Temp In (°C):", value=15)
    source_temp_out = st.number_input("Source Temp Out (°C):", value=9)

with col2:
    sink_temp_in = st.number_input("Sink Temp In (District Return, °C):", value=40)
    sink_temp_out = st.number_input("Sink Temp Out (District Supply, °C):", value=70)

if st.button("Calculate"):
    with st.spinner('Calculating...'):
        results, cop = run_simulation(fluid_choice, source_temp_in, source_temp_out, sink_temp_in, sink_temp_out)

    st.success("Calculation Complete")

    st.header("Results")
    st.write(f"Coefficient of Performance (COP): {cop:.2f}")

    for comp, res in results.items():
        st.subheader(f"{comp}")
        st.dataframe(res)
