from tespy.networks import Network
from tespy.components import (
    Sink, Source, Pump, HeatExchanger, Compressor, Valve, CycleCloser
)
from tespy.connections import Connection
from tespy.tools.characteristics import CharLine
import numpy as np


def run_simulation(working_fluid, sink_return, sink_supply, source_in, source_out):
    fluids = [working_fluid, "water"]
    nw = Network(fluids=fluids, p_unit="bar", T_unit="C", h_unit="kJ / kg")

    # Components
    cc = CycleCloser("Cycle closer")
    source = Source("heat source")
    sink = Sink("heat sink")
    pump = Pump("pump")
    evaporator = HeatExchanger("evaporator")
    condenser = HeatExchanger("condenser")
    valve = Valve("expansion valve")
    compressor = Compressor("compressor")

    # Connections (main loop)
    c1 = Connection(valve, "out1", evaporator, "in1", label="1")
    c2 = Connection(evaporator, "out1", compressor, "in1", label="2")
    c3 = Connection(compressor, "out1", condenser, "in1", label="3")
    c4 = Connection(condenser, "out1", valve, "in1", label="4")
    nw.add_conns(c1, c2, c3, c4)

    # Source side (wastewater)
    src = Source("wastewater inlet")
    snk = Sink("wastewater outlet")
    he1 = HeatExchanger("evaporator")  # external heat exchanger
    c17 = Connection(src, "out1", he1, "in1", label="17")
    c19 = Connection(he1, "out1", snk, "in1", label="19")
    nw.add_conns(c17, c19)

    # Sink side (district heating)
    cons = Source("district return")
    supply = Sink("district supply")
    he2 = HeatExchanger("condenser")  # external heat exchanger
    c20 = Connection(cons, "out1", he2, "in1", label="20")
    c22 = Connection(he2, "out1", supply, "in1", label="22")
    nw.add_conns(c20, c22)

    # Set fluid
    for c in [c1, c2, c3, c4]:
        c.set_attr(fluid={working_fluid: 1})

    # Set source side temperatures
    c17.set_attr(T=source_in, fluid={"water": 1})
    c19.set_attr(T=source_out, p=1.013)

    # Set sink side temperatures
    c20.set_attr(T=sink_return, fluid={"water": 1}, p=3)
    c22.set_attr(T=sink_supply)

    # Main refrigerant pressure assumptions
    c1.set_attr(x=0.95)
    c3.set_attr(T=90)

    # Compressor efficiency
    compressor.set_attr(eta_s=0.85)

    # Solve
    nw.solve("design")
    nw.print_results()

    # Calculate COP
    Q_condenser = condenser.Q.val  # in kW
    W_comp = compressor.P.val  # in kW
    cop = Q_condenser / W_comp if W_comp != 0 else 0

    return cop, {
        "Q_condenser_kW": Q_condenser,
        "W_compressor_kW": W_comp
    }
