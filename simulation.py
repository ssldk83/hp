from tespy.networks import Network
from tespy.components import Source, Sink, Pump, HeatExchanger, Compressor, Valve, CycleCloser
from tespy.connections import Connection
import numpy as np


def run_simulation(working_fluid, sink_return, sink_supply, source_in, source_out):
    fluids = [working_fluid, "water"]
    nw = Network(T_unit='C', p_unit='bar', h_unit='kJ / kg', fluids=fluids)

    # Components
    # Refrigerant side
    cc = CycleCloser("cycle closer")
    src_r = Source("refrigerant source")
    evap = HeatExchanger("evaporator")
    comp = Compressor("compressor")
    cond = HeatExchanger("condenser")
    valve = Valve("valve")

    # Sink side (district heating)
    src_sink = Source("district return")
    pump_sink = Pump("sink pump")
    sink = Sink("district supply")

    # Source side (wastewater)
    src_source = Source("wastewater inlet")
    pump_source = Pump("source pump")
    sink_source = Sink("wastewater outlet")

    # Refrigerant cycle connections
    c0 = Connection(src_r, "out1", evap, "in1", label="0")
    c1 = Connection(evap, "out1", comp, "in1", label="1")
    c2 = Connection(comp, "out1", cond, "in1", label="2")
    c3 = Connection(cond, "out1", valve, "in1", label="3")
    c4 = Connection(valve, "out1", cc, "in1", label="4")
    c5 = Connection(cc, "out1", evap, "in1", label="5")

    # Sink side connections
    c20 = Connection(src_sink, "out1", cond, "in2", label="20")
    c21 = Connection(cond, "out2", pump_sink, "in1", label="21")
    c22 = Connection(pump_sink, "out1", sink, "in1", label="22")

    # Source side connections
    c10 = Connection(src_source, "out1", pump_source, "in1", label="10")
    c11 = Connection(pump_source, "out1", evap, "in2", label="11")
    c12 = Connection(evap, "out2", sink_source, "in1", label="12")

    # Add to network
    nw.add_conns(c0, c1, c2, c3, c4, c5,
                 c10, c11, c12,
                 c20, c21, c22)

    # Fluid settings
    c0.set_attr(fluid={working_fluid: 1})
    c5.set_attr(fluid={working_fluid: 1})
    c10.set_attr(T=source_in, fluid={"water": 1})
    c12.set_attr(T=source_out)
    c20.set_attr(T=sink_return, fluid={"water": 1})
    c22.set_attr(p=1.013)
    c21.set_attr(T=sink_supply)

    # Pressures
    c1.set_attr(p=8)
    c3.set_attr(p=3)

    # Efficiencies
    comp.set_attr(eta_s=0.85)
    pump_sink.set_attr(eta_s=0.8)
    pump_source.set_attr(eta_s=0.8)

    # Run simulation
    nw.solve(mode="design")
    cop = cond.Q.val / comp.P.val

    return round(cop, 2), nw.res
