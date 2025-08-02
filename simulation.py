# simulation.py

from tespy.networks import Network
from tespy.components import (
    Source, Sink, Pump, Compressor, Valve, HeatExchanger, CycleCloser
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
    nw = Network(
        fluids=[working_fluid, "water"],
        T_unit="C", p_unit="bar", h_unit="kJ / kg", m_unit="kg / s"
    )

    # Refrigeration cycle components
    cc = CycleCloser("cycle_closer")
    evap = HeatExchanger("evaporator")
    comp = Compressor("compressor")
    cond = HeatExchanger("condenser")
    valve = Valve("expansion_valve")

    # Source and sink for refrigerant loop
    src_rf = Source("src_refrigerant")
    sink_rf = Sink("snk_refrigerant")

    # District heating sink loop (external)
    src_sink = Source("district_return")
    snk_sink = Sink("district_supply")
    cond_ext = HeatExchanger("condenser_external")

    # Wastewater source loop (external)
    src_waste = Source("wastewater_in")
    snk_waste = Sink("wastewater_out")
    evap_ext = HeatExchanger("evaporator_external")

    # Connect refrigeration loop
    c0 = Connection(src_rf, "out1", evap, "in1", label="0")
    c1 = Connection(evap, "out1", comp, "in1", label="1")
    c2 = Connection(comp, "out1", cond, "in1", label="2")
    c3 = Connection(cond, "out1", valve, "in1", label="3")
    c4 = Connection(valve, "out1", cc, "in1", label="4")
    c5 = Connection(cc, "out1", src_rf, "in1", label="5")

    # Connect district heating sink
    c20 = Connection(src_sink, "out1", cond_ext, "in1", label="20")
    c22 = Connection(cond_ext, "out1", snk_sink, "in1", label="22")

    # Connect wastewater source
    c17 = Connection(src_waste, "out1", evap_ext, "in1", label="17")
    c19 = Connection(evap_ext, "out1", snk_waste, "in1", label="19")

    nw.add_conns(c0, c1, c2, c3, c4, c5, c20, c22, c17, c19)

    # Set refrigerant flow and state guesses
    for c in (c0, c1, c2, c3, c4, c5):
        c.set_attr(fluid={working_fluid: 1})

    # Condenser pressure based on fluid default cond_T
    p_cond = PropsSI("P", "Q", 1, "T", 273.15 + defaults["cond_T"], working_fluid) / 1e5
    c2.set_attr(T=defaults["inlet_T"], p=p_cond)

    # District heating side
    c20.set_attr(T=sink_return, fluid={"water": 1})
    c22.set_attr(T=sink_supply)

    # Wastewater source side
    c17.set_attr(T=source_in, fluid={"water": 1})
    c19.set_attr(T=source_out)

    # Refrigerant interpolated settings
    evap.set_attr(x=0.95)
    comp.set_attr(eta_s=0.8)
    cond.set_attr(pr1=0.99, pr2=0.99)
    valve.set_attr()

    # Set characteristic lines for external HX
    kA = CharLine([0, 1], [0, 1])
    evap_ext.set_attr(kA_char1=kA, kA_char2=kA)
    cond_ext.set_attr(kA_char1=kA, kA_char2=kA)

    # Solve design & offdesign
    nw.solve("design")
    with NamedTemporaryFile(delete=False, suffix=".json") as tmp:
        path = tmp.name
        nw.save(path)
    nw.solve("offdesign", design_path=path)
    os.remove(path)

    # COP calculation
    q_cond = cond.Q.val
    w_comp = comp.P.val
    cop = abs(q_cond) / w_comp if w_comp else None

    results = {
        "COP": cop,
        "Q_cond": q_cond,
        "W_comp": w_comp
    }
    # You can also fetch other connection results here via nw.results
    return cop, results
