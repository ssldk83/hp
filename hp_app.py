import streamlit as st
from hp_app import HeatPumpCalculator, Refrigerant, HeatSource

st.title("Heat Pump COP Calculator")

st.write(
    "Select a refrigerant and heat source to estimate the coefficient of performance "
    "(COP) for a district heating application. These calculations use simplified "
    "thermodynamic correlations and are intended for educational purposes."
)

# Input selections
refrigerant = st.selectbox(
    "Refrigerant",
    list(Refrigerant),
    format_func=lambda r: r.value
)

heat_source = st.selectbox(
    "Heat Source",
    list(HeatSource),
    format_func=lambda h: h.value
)

dh_supply = st.number_input(
    "District Heating Supply Temperature (°C)",
    value=70.0,
)


dh_return = st.number_input(
    "District Heating Return Temperature (°C)",
    value=40.0,
)

ambient_temp = st.number_input(
    "Ambient Temperature for Air Source (°C)",
    value=10.0,
)

if st.button("Calculate COP"):
    calc = HeatPumpCalculator()
    result = calc.calculate_system_performance(
        heat_source,
        refrigerant,
        district_heating_supply_temp=dh_supply,
        district_heating_return_temp=dh_return,
        ambient_temp=ambient_temp,
    )

    if result.get("status") == "OK":
        st.subheader("Operating Conditions")
        st.write(f"Source temperature range: {result['source_temp_range']}")
        st.write(f"Evaporator temperature: {result['evaporator_temp']:.1f} °C")
        st.write(f"Condenser temperature: {result['condenser_temp']:.1f} °C")
        st.write(f"Temperature lift: {result['temp_lift']:.1f} K")
        st.write(f"Operation mode: {result['operation_mode']}")

        st.subheader("Performance")
        st.write(f"COP Heating: {result['cop_heating']:.2f}")
        st.write(f"COP Cooling: {result['cop_cooling']:.2f}")
        st.write(f"Carnot COP: {result['cop_carnot']:.2f}")
        st.write(f"Carnot efficiency: {result['carnot_efficiency']:.1%}")
        st.write(f"Discharge temperature: {result['discharge_temp']:.1f} °C")
        st.write(f"Pressure ratio: {result['pressure_ratio']:.2f}")
        st.write(f"Evaporator pressure: {result['evaporator_pressure']:.2f} bar")
        if 'condenser_pressure' in result:
            st.write(
                f"Condenser pressure: {result['condenser_pressure']:.2f} bar"
            )
        if 'gas_cooler_pressure' in result:
            st.write(
                f"Gas cooler pressure: {result['gas_cooler_pressure']:.2f} bar"
            )
    else:
        st.error(result.get("error_message", "Unknown error"))
