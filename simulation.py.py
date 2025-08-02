# simulation.py

import os
from tespy.networks import Network
from tespy.components import (
    Condenser, CycleCloser, SimpleHeatExchanger, Pump, Sink, Source,
    Valve, Drum, HeatExchanger, Compressor, Splitter, Merge
)
from tespy.connections import Connection
from tespy.tools.characteristics import CharLine
from CoolProp.CoolProp import PropsSI
from tempfile import NamedTemporaryFile


fluid_defaults = {
    "NH3": {"cond_T": 95, "inlet_T": 170},
    "Propane": {"cond_T": 50, "inlet_T": 120},
    "Isobutane": {"cond_T": 45, "inlet_T": 110}
}


def run_simulation(working_fluid, sink_return, sink_supply, source_in, source_out):
    defaults = fluid_defaults[working_fluid]
    nw = Network(T_unit="C", p_unit="bar", h_unit="kJ / kg", m_unit="kg / s")

    # Define your components (same as your original file)
    c_in = Source("refrigerant in")
    cons_closer = CycleCloser("consumer cycle closer")
    va = Sink("valve")
    cd = Condenser("condenser")
    rp = Pump("recirculation pump")
    cons = SimpleHeatExchanger("consumer")

    c0 = Connection(c_in, "out1", cd, "in1", label="0")
    c1 = Connection(cd, "out1", va, "in1", label="1")
    c20 = Connection(cons_closer, "out1", rp, "in1", label="20")
    c21 = Connection(rp, "out1", cd, "in2", label="21")
    c22 = Connection(cd, "out2", cons, "in1", label="22")
    c23 = Connection(cons, "out1", cons_closer, "in1", label="23")
    nw.add_conns(c0, c1, c20, c21, c22, c23)

    cd.set_attr(pr1=0.99, pr2=0.99)
    rp.set_attr(eta_s=0.75)
    cons.set_attr(pr=0.99)

    p_cond = PropsSI("P", "Q", 1, "T", 273.15 + defaults["cond_T"], working_fluid) / 1e5
    c0.set_attr(T=defaults["inlet_T"], p=p_cond, fluid={working_fluid: 1})
    c20.set_attr(T=sink_return, p=2, fluid={"water": 1})
    c22.set_attr(T=sink_supply)
    cons.set_attr(Q=-230e3)

    nw.solve("design")

    # Continue with the rest of the setup (evaporator, compressors, etc.)
    # Reuse from your working 195-line file (unchanged logic except for c17/c19 below)

    # Source temperature updates
    c17.set_attr(T=source_in, fluid={"water": 1})
    c19.set_attr(T=source_out, p=1.013)

    # Final steps
    q_out = cons.Q.val
    w_in = cp1.P.val + cp2.P.val + rp.P.val + hsp.P.val
    cop = abs(q_out) / w_in if w_in else None
    results = {k: v.to_dict() for k, v in nw.results.items()}
    return cop, results
