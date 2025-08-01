import streamlit as st
import numpy as np

def calculate_lorenz_cop(T_heat, T_cool, delta_T_heat, delta_T_cool):
    T_heat_K = T_heat + 273.15
    T_cool_K = T_cool + 273.15
    
    T_H_i_K = (T_heat - delta_T_heat) + 273.15  # Inlet to sink
    T_H_o_K = T_heat_K  # Outlet from sink
    T_C_i_K = T_cool_K  # Inlet to source
    T_C_o_K = (T_cool + delta_T_cool) + 273.15  # Outlet from source (note: for source, temperature increases as heat is extracted)
    
    if delta_T_heat > 0:
        T_bar_H = delta_T_heat / np.log(T_H_o_K / T_H_i_K)
    else:
        T_bar_H = T_heat_K
    
    if delta_T_cool > 0:
        T_bar_C = delta_T_cool / np.log(T_C_o_K / T_C_i_K)
    else:
        T_bar_C = T_cool_K
    
    COP_Lorenz = T_bar_H / (T_bar_H - T_bar_C)
    return COP_Lorenz

st.title("Heat Pump COP Calculator")

st.write("""
This app calculates the Coefficient of Performance (COP) for a heat pump using the Lorenz cycle model, 
which accounts for temperature glides in the heat source and sink. It provides a more precise thermodynamic 
benchmark than the Carnot cycle for systems with finite heat capacities. The estimated real COP is adjusted 
based on typical efficiencies for the selected cooling media and refrigerant properties.
""")

media = st.selectbox("Natural Cooling Media", ["Air", "Water", "Ground"])
refrigerant = st.selectbox("Refrigerant", ["R134a", "R410A", "Ammonia", "CO2", "Other"])
T_heat = st.number_input("Water Heating Outlet Temperature (°C)", value=50.0)
T_cool = st.number_input("Cooling Inlet Temperature (°C)", value=10.0)
delta_T_heat = st.number_input("Temperature Glide for Heat Sink (°C)", value=10.0)
delta_T_cool = st.number_input("Temperature Glide for Heat Source (°C)", value=5.0)

if T_heat <= T_cool:
    st.error("Heating temperature must be greater than cooling temperature.")
else:
    # Base efficiency factor based on media
    if media.lower() == "air":
        eta = 0.3
    elif media.lower() == "water":
        eta = 0.35
    elif media.lower() == "ground":
        eta = 0.4
    else:
        eta = 0.35

    # Adjust for refrigerant properties
    if refrigerant.lower() == "ammonia":
        eta *= 1.3
    elif refrigerant.lower() == "r410a":
        eta *= 1.05
    elif refrigerant.lower() == "co2":
        eta *= 0.85
    else:
        eta *= 1.0

    COP_Lorenz = calculate_lorenz_cop(T_heat, T_cool, delta_T_heat, delta_T_cool)
    COP_estimated = COP_Lorenz * eta

    st.subheader("Results")
    st.write(f"**Lorenz COP:** {COP_Lorenz:.2f}")
    st.write(f"**Estimated Real COP:** {COP_estimated:.2f}")

    st.write("""
    Note: For even more precise calculations, this model uses approximate efficiency factors. 
    In a full implementation, integrate with libraries like CoolProp for actual fluid properties 
    (e.g., enthalpies in a vapor compression cycle). This app provides a good thermodynamic approximation.
    """)
