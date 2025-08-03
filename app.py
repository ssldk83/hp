import streamlit as st
from CoolProp.CoolProp import PropsSI as PSI
from tespy.networks import Network
from tespy.components import (Source, Sink, CycleCloser, Compressor, Condenser, Valve,
                              Pump, HeatExchanger, Drum, SimpleHeatExchanger, Splitter, Merge)
from tespy.connections import Connection
from tespy.tools.characteristics import CharLine
from tespy.tools.characteristics import load_default_char as ldc

st.set_page_config(layout="wide")
st.title("Heat Pump H&MB Calculator")

fluid_choice = st.selectbox("Select Refrigerant:", ["Propane", "Isobutane", "NH3"])
source_choice = st.selectbox("Select Heat Source:", ["Wastewater", "Air", "Datacenter"])

col1, col2 = st.columns(2)
with col1:
    source_temp_in = st.number_input("Source Temp In (°C):", value=10.1)
    source_temp_out = st.number_input("Source Temp Out (°C):", value=3.5)

with col2:
    sink_temp_in = st.number_input("Sink Temp In (District Return, °C):", value=45)
    sink_temp_out = st.number_input("Sink Temp Out (District Supply, °C):", value=70)

if st.button("Calculate"):
    with st.spinner('Running simulation...'):
        try:
            working_fluid = fluid_choice
            nw = Network(T_unit="C", p_unit="bar", h_unit="kJ / kg", m_unit="kg / s")
            # Components
            cc = CycleCloser("cycle closer")
            cd = Condenser("condenser")
            va = Valve("valve")
            dr = Drum("drum")
            ev = HeatExchanger("evaporator")
            su = HeatExchanger("superheater")
            cp1 = Compressor("compressor 1")
            cp2 = Compressor("compressor 2")
            ic = HeatExchanger("intermittent cooling")
            rp = Pump("recirculation pump")
            cons = SimpleHeatExchanger("consumer")
            hsp = Pump("heat source pump")
            sp = Splitter("splitter")
            me = Merge("merge")
            cv = Valve("control valve")
            hs = Source("ambient intake")
            amb_out = Sink("ambient out")
            cons_closer = CycleCloser("consumer cycle closer")
            sink = Sink("sink")
            source = Source("source")

            # Connections
            p_cond = PSI("P", "Q", 1, "T", 273.15 + sink_temp_out, working_fluid) / 1e5
            c0 = Connection(cc, "out1", cd, "in1", label="0")
            c1 = Connection(cd, "out1", va, "in1", label="1")
            c1 = Connection(cd, "out1", va, "in1", label="1")
            c2 = Connection(va, "out1", dr, "in1", label="2")
            c3 = Connection(dr, "out1", ev, "in2", label="3")
            c4 = Connection(ev, "out2", dr, "in2", label="4")
            c5 = Connection(dr, "out2", su, "in2", label="5")
            c6 = Connection(su, "out2", cp1, "in1", label="6")
            c7 = Connection(cp1, "out1", ic, "in1", label="7")
            c8 = Connection(ic, "out1", cp2, "in1", label="8")
            c9 = Connection(cp2, "out1", cc, "in1", label="9")
            c11 = Connection(hs, "out1", hsp, "in1", label="11")
            c12 = Connection(hsp, "out1", sp, "in1", label="12")
            c13 = Connection(sp, "out1", ic, "in2", label="13")
            c14 = Connection(ic, "out2", me, "in1", label="14")
            c15 = Connection(sp, "out2", cv, "in1", label="15")
            c16 = Connection(cv, "out1", me, "in2", label="16")
            c17 = Connection(me, "out1", su, "in1", label="17")
            c18 = Connection(su, "out1", ev, "in1", label="18")
            c19 = Connection(ev, "out1", amb_out, "in1", label="19")
            c20 = Connection(cons_closer, "out1", rp, "in1", label="20")
            c21 = Connection(rp, "out1", cd, "in2", label="21")
            c22 = Connection(cd, "out2", cons, "in1", label="22")
            c23 = Connection(cons, "out1", cons_closer, "in1", label="23")
            nw.add_conns(c0, c1, c2, c3, c4, c5, c6, c7, c8, c9, c11, c12, c13, c14, c15, c16, c17, c20, c21, c22, c23)

            # Boundary conditions
            c0.set_attr(p=p_cond, fluid={working_fluid: 1})
            c20.set_attr(T=sink_temp_in, p=2, fluid={"water": 1})
            c22.set_attr(T=sink_temp_out)
            c4.set_attr(x=0.9, T=source_temp_out)
            h_sat = PSI("H", "Q", 1, "T", 273.15 + source_temp_in, working_fluid) / 1e3
            c6.set_attr(h=h_sat)
            c11.set_attr(p=1.013, T=source_temp_in, fluid={"water": 1})
            c14.set_attr(T=source_temp_out)

            # Component attributes
            cd.set_attr(pr1=0.99, pr2=0.99, ttd_u=5)
            ev.set_attr(pr1=0.99, ttd_l=5)
            su.set_attr(pr1=0.99, pr2=0.99, ttd_u=5)
            ic.set_attr(pr1=0.99, pr2=0.98)
            rp.set_attr(eta_s=0.75)
            hsp.set_attr(eta_s=0.75)
            cp1.set_attr(eta_s=0.8)
            cp2.set_attr(eta_s=0.8)
            cons.set_attr(Q=-230e3, pr=0.99)

            nw.solve("design")

            # Calculate performance
            q_out = cons.Q.val
            w_in = cp1.P.val + cp2.P.val + rp.P.val + hsp.P.val
            cop = abs(q_out) / w_in if w_in != 0 else None

            # Prepare results
            results = {k: v.to_dict("index") for k, v in nw.results.items()}
            value_map = {
                "COP": round(cop, 2),
                "Q_out (kW)": round(q_out / 1e3, 1),
                "W_in (kW)": round(w_in / 1e3, 1),
                "T_source_in": source_temp_in,
                "T_source_out": source_temp_out,
                "T_sink_in": sink_temp_in,
                "T_sink_out": sink_temp_out,
            }

            st.success("Calculation Complete")
            st.header("Results")
            st.write(f"Coefficient of Performance (COP): {cop:.2f}")

            st.subheader("Key Values")
            for label, val in value_map.items():
                st.write(f"{label}: {val}")

            # Load and modify SVG
            svg_path = Path("/mnt/data/hp_sample.svg")
            svg_content = svg_path.read_text()
            for i, (label, val) in enumerate(value_map.items()):
                svg_content += f'<text x="20" y="{40 + i * 20}" font-size="14" fill="red">{label}: {val}</text>'
            b64_svg = base64.b64encode(svg_content.encode("utf-8")).decode("utf-8")
            st.markdown(f'<object type="image/svg+xml" data="data:image/svg+xml;base64,{b64_svg}" width="100%"></object>', unsafe_allow_html=True)

        except Exception as e:
            st.error(f"An error occurred: {e}")
