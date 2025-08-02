from tespy.components import (Sink, Source, Pump, HeatExchanger, Compressor, Valve,
                               CycleCloser)
from tespy.connections import Connection
from tespy.networks import Network
from tespy.tools.characteristics import CharLine
import numpy as np

def run_simulation(fluid, t_sink_in, t_sink_out, t_source_in, t_source_out):
    # Set up the network
    fluids = [fluid, "water"]
    nw = Network(fluids=fluids, T_unit='C', p_unit='bar', h_unit='kJ / kg', m_unit='kg / s')

    # Components
    # Refrigerant loop
    cc = CycleCloser('cycle closer')
    evap = HeatExchanger('evaporator')
    comp = Compressor('compressor')
    cond = HeatExchanger('condenser')
    valve = Valve('expansion valve')

    # Source/sink loop
    src_w = Source('wastewater source')
    sink_w = Sink('wastewater sink')
    src_dh = Source('district return')
    sink_dh = Sink('district supply')

    # Connections: Refrigerant cycle
    c0 = Connection(cc, "out1", evap, "in1", label="0")
    c1 = Connection(evap, "out1", comp, "in1", label="1")
    c2 = Connection(comp, "out1", cond, "in1", label="2")
    c3 = Connection(cond, "out1", valve, "in1", label="3")
    c4 = Connection(valve, "out1", cc, "in1", label="4")

    # Connections: Source side (wastewater)
    c10 = Connection(src_w, "out1", evap, "in2", label="10")
    c11 = Connection(evap, "out2", sink_w, "in1", label="11")

    # Connections: Sink side (district heating)
    c20 = Connection(src_dh, "out1", cond, "in2", label="20")
    c21 = Connection(cond, "out2", sink_dh, "in1", label="21")

    # Add to network
    nw.add_conns(c0, c1, c2, c3, c4, c10, c11, c20, c21)

    # Parametrize
    c10.set_attr(T=t_source_in, fluid={"water": 1})
    c11.set_attr(T=t_source_out)
    c20.set_attr(T=t_sink_in, fluid={"water": 1})
    c21.set_attr(T=t_sink_out)
    c0.set_attr(fluid={fluid: 1})

    comp.set_attr(eta_s=0.8)

    # Solve
    nw.solve(mode="design")
    cop = c2.h.val / (c2.h.val - c1.h.val)

    return round(cop, 2), nw.res
