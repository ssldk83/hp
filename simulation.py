from tespy.components import (Sink, Source, Pump, HeatExchanger, Compressor, Valve, CycleCloser)
from tespy.connections import Connection
from tespy.networks import Network
import numpy as np


def run_simulation(fluid, t_sink_in, t_sink_out, t_source_in, t_source_out):
    # Define fluids
    fluids = [fluid, "water"]

    # Network
    nw = Network(
        fluids=fluids,
        T_unit='C',
        p_unit='bar',
        h_unit='kJ / kg',
        m_unit='kg / s'
    )

    # Refrigerant loop
    cc = CycleCloser('cycle closer')
    evap = HeatExchanger('evaporator')
    comp = Compressor('compressor')
    cond = HeatExchanger('condenser')
    valve = Valve('expansion valve')

    # Water side
    src_w = Source('wastewater source')
    sink_w = Sink('wastewater sink')
    src_dh = Source('district return')
    sink_dh = Sink('district supply')

    # Connections - Refrigerant cycle
    c0 = Connection(cc, 'out1', evap, 'in1')
    c1 = Connection(evap, 'out1', comp, 'in1')
    c2 = Connection(comp, 'out1', cond, 'in1')
    c3 = Connection(cond, 'out1', valve, 'in1')
    c4 = Connection(valve, 'out1', cc, 'in1')

    # Connections - Wastewater source side
    c10 = Connection(src_w, 'out1', evap, 'in2')
    c11 = Connection(evap, 'out2', sink_w, 'in1')

    # Connections - District heating sink side
    c20 = Connection(src_dh, 'out1', cond, 'in2')
    c21 = Connection(cond, 'out2', sink_dh, 'in1')

    nw.add_conns(c0, c1, c2, c3, c4, c10, c11, c20, c21)

    # Boundary conditions
    c0.set_attr(fluid={fluid: 1})
    c10.set_attr(T=t_source_in, p=2, fluid={"water": 1})
    c11.set_attr(T=t_source_out, p=2)
    c20.set_attr(T=t_sink_in, p=3, fluid={"water": 1})
    c21.set_attr(T=t_sink_out, p=3)

    # Component attributes
    comp.set_attr(eta_s=0.8)
    evap.set_attr(pr1=0.98, pr2=0.98, Q=-1e5)
    cond.set_attr(pr1=0.98, pr2=0.98)

    # Solve
    nw.solve(mode='design')
    nw.print_results()

    # COP calculation
    cop = c2.h.val / (c2.h.val - c1.h.val)
    return round(cop, 2), nw.res
