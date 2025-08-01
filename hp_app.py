import math
import numpy as np
from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from enum import Enum

class Refrigerant(Enum):
    """Supported refrigerants"""
    PROPANE = "R290"
    ISOBUTANE = "R600a"
    PROPYLENE = "R1270"
    AMMONIA = "R717"
    CO2 = "R744"

class HeatSource(Enum):
    """Available heat sources"""
    AIR = "Air"
    WASTEWATER = "Wastewater"
    DATACENTER_WATER = "Datacenter Water"

@dataclass
class RefrigerantProperties:
    """Refrigerant thermodynamic properties"""
    name: str
    critical_temp: float  # °C
    critical_pressure: float  # bar
    boiling_point: float  # °C at 1 atm
    molecular_weight: float  # g/mol
    cp_cv_ratio: float  # Heat capacity ratio (gamma)
    # Antoine equation coefficients
    antoine_a: float
    antoine_b: float
    antoine_c: float
    # Additional properties for better accuracy
    acentric_factor: float
    specific_heat_vapor: float  # kJ/kg·K at 25°C

# Enhanced refrigerant properties database
REFRIGERANT_PROPERTIES = {
    Refrigerant.PROPANE: RefrigerantProperties(
        name="Propane (R290)",
        critical_temp=96.74,
        critical_pressure=42.51,
        boiling_point=-42.1,
        molecular_weight=44.1,
        cp_cv_ratio=1.13,
        antoine_a=15.726,
        antoine_b=1872.46,
        antoine_c=-25.16,
        acentric_factor=0.152,
        specific_heat_vapor=1.67
    ),
    Refrigerant.ISOBUTANE: RefrigerantProperties(
        name="Isobutane (R600a)",
        critical_temp=134.66,
        critical_pressure=36.40,
        boiling_point=-11.7,
        molecular_weight=58.12,
        cp_cv_ratio=1.10,
        antoine_a=15.854,
        antoine_b=2348.67,
        antoine_c=-27.85,
        acentric_factor=0.181,
        specific_heat_vapor=1.66
    ),
    Refrigerant.PROPYLENE: RefrigerantProperties(
        name="Propylene (R1270)",
        critical_temp=91.06,
        critical_pressure=45.55,
        boiling_point=-47.6,
        molecular_weight=42.08,
        cp_cv_ratio=1.15,
        antoine_a=15.7027,
        antoine_b=1807.53,
        antoine_c=-26.15,
        acentric_factor=0.146,
        specific_heat_vapor=1.53
    ),
    Refrigerant.AMMONIA: RefrigerantProperties(
        name="Ammonia (R717)",
        critical_temp=132.25,
        critical_pressure=113.33,
        boiling_point=-33.34,
        molecular_weight=17.03,
        cp_cv_ratio=1.31,
        antoine_a=16.9481,
        antoine_b=2132.50,
        antoine_c=-32.98,
        acentric_factor=0.256,
        specific_heat_vapor=2.06
    ),
    Refrigerant.CO2: RefrigerantProperties(
        name="Carbon Dioxide (R744)",
        critical_temp=31.06,
        critical_pressure=73.77,
        boiling_point=-78.46,
        molecular_weight=44.01,
        cp_cv_ratio=1.30,
        antoine_a=22.5898,
        antoine_b=3103.39,
        antoine_c=-0.16,
        acentric_factor=0.225,
        specific_heat_vapor=0.844
    )
}

class HeatPumpCalculator:
    def __init__(self):
        self.compressor_efficiency = 0.75  # Isentropic efficiency
        self.mechanical_efficiency = 0.95  # Mechanical/electrical efficiency
        self.heat_exchanger_effectiveness = 0.85  # Heat exchanger effectiveness
        self.pressure_drop_ratio = 0.02  # 2% pressure drop in heat exchangers
        
    def get_heat_source_temp(self, source: HeatSource, ambient_temp: float = 10.0) -> Tuple[float, float]:
        """Get typical temperature range for heat sources"""
        if source == HeatSource.AIR:
            return (ambient_temp - 5, ambient_temp)
        elif source == HeatSource.WASTEWATER:
            return (10, 20)
        elif source == HeatSource.DATACENTER_WATER:
            return (20, 35)
    
    def calculate_saturation_pressure(self, temp: float, refrigerant: Refrigerant) -> float:
        """Calculate saturation pressure using Antoine equation"""
        props = REFRIGERANT_PROPERTIES[refrigerant]
        
        # Special handling for CO2 near critical point
        if refrigerant == Refrigerant.CO2 and temp > 25:
            # Use Wagner equation approximation for CO2
            Tr = (temp + 273.15) / (props.critical_temp + 273.15)
            tau = 1 - Tr
            
            if tau <= 0:
                return props.critical_pressure
            
            # Wagner equation coefficients for CO2
            a1, a2, a3, a4 = -7.0602, 1.9391, -1.6463, -3.2995
            n1, n2, n3, n4 = 1, 1.5, 2, 4
            
            ln_pr = (a1 * tau**n1 + a2 * tau**n2 + a3 * tau**n3 + a4 * tau**n4) / Tr
            return props.critical_pressure * math.exp(ln_pr)
        
        # Antoine equation for other refrigerants
        if temp < -200:  # Prevent numerical errors
            return 0.001
            
        log_p_mmhg = props.antoine_a - props.antoine_b / (props.antoine_c + temp)
        p_mmhg = 10 ** log_p_mmhg
        p_bar = p_mmhg * 0.00133322
        
        return p_bar
    
    def calculate_enthalpy_change(self, T1: float, T2: float, P1: float, P2: float, 
                                 refrigerant: Refrigerant, is_vapor: bool = True) -> float:
        """Estimate enthalpy change using thermodynamic relations"""
        props = REFRIGERANT_PROPERTIES[refrigerant]
        
        if is_vapor:
            # For vapor phase, use ideal gas approximation with corrections
            cp = props.specific_heat_vapor
            R = 8.314 / props.molecular_weight  # kJ/kg·K
            
            # Temperature contribution
            dh_temp = cp * (T2 - T1)
            
            # Pressure correction (departure from ideal gas)
            # Using simplified Peng-Robinson type correction
            Tr1 = (T1 + 273.15) / (props.critical_temp + 273.15)
            Tr2 = (T2 + 273.15) / (props.critical_temp + 273.15)
            Pr1 = P1 / props.critical_pressure
            Pr2 = P2 / props.critical_pressure
            
            # Departure function
            Z1 = 1 - 0.08 * Pr1 / Tr1  # Simplified compressibility
            Z2 = 1 - 0.08 * Pr2 / Tr2
            
            dh_pressure = R * T1 * (Z2 - Z1)
            
            return dh_temp + dh_pressure
        else:
            # For liquid phase, assume incompressible
            return props.specific_heat_vapor * 0.5 * (T2 - T1)  # Rough approximation
    
    def calculate_latent_heat(self, temp: float, refrigerant: Refrigerant) -> float:
        """Estimate latent heat of vaporization using Watson equation"""
        props = REFRIGERANT_PROPERTIES[refrigerant]
        
        # Reference latent heat at normal boiling point (rough estimates in kJ/kg)
        h_fg_ref = {
            Refrigerant.PROPANE: 425,
            Refrigerant.ISOBUTANE: 367,
            Refrigerant.PROPYLENE: 439,
            Refrigerant.AMMONIA: 1369,
            Refrigerant.CO2: 234  # At -40°C
        }
        
        if temp >= props.critical_temp:
            return 0
        
        # Watson equation
        Tr = (temp + 273.15) / (props.critical_temp + 273.15)
        Tr_ref = (props.boiling_point + 273.15) / (props.critical_temp + 273.15)
        
        n = 0.38  # Watson exponent
        h_fg = h_fg_ref[refrigerant] * ((1 - Tr) / (1 - Tr_ref)) ** n
        
        return max(0, h_fg)
    
    def calculate_cop_real(self, t_evap: float, t_cond: float, refrigerant: Refrigerant,
                          subcooling: float = 5, superheat: float = 5) -> Dict[str, float]:
        """Calculate real COP using thermodynamic cycle analysis"""
        
        props = REFRIGERANT_PROPERTIES[refrigerant]
        
        # Check for transcritical operation
        if t_cond >= props.critical_temp:
            if refrigerant == Refrigerant.CO2:
                return self._calculate_cop_transcritical_co2(t_evap, t_cond, subcooling, superheat)
            else:
                raise ValueError(f"Condenser temperature {t_cond}°C exceeds critical "
                               f"temperature {props.critical_temp}°C for {props.name}")
        
        # Calculate pressures
        p_evap = self.calculate_saturation_pressure(t_evap, refrigerant)
        p_cond = self.calculate_saturation_pressure(t_cond, refrigerant)
        
        # Apply pressure drops
        p_evap_out = p_evap * (1 - self.pressure_drop_ratio)
        p_cond_in = p_cond * (1 + self.pressure_drop_ratio)
        
        # Temperature values
        T1 = t_evap + superheat  # Compressor inlet
        T3 = t_cond - subcooling  # Condenser outlet
        
        # Estimate discharge temperature using polytropic compression
        gamma = props.cp_cv_ratio
        n = 1 + (gamma - 1) / (gamma * self.compressor_efficiency)  # Polytropic exponent
        
        T1_K = T1 + 273.15
        T2_K = T1_K * (p_cond_in / p_evap_out) ** ((n - 1) / n)
        T2 = T2_K - 273.15
        
        # Calculate enthalpy differences
        # Compression work
        h_comp = self.calculate_enthalpy_change(T1, T2, p_evap_out, p_cond_in, refrigerant, is_vapor=True)
        
        # Heat rejection in condenser
        # Desuperheating + Condensation + Subcooling
        h_desuper = props.specific_heat_vapor * (T2 - t_cond)
        h_fg_cond = self.calculate_latent_heat(t_cond, refrigerant)
        h_subcool = props.specific_heat_vapor * 0.5 * subcooling  # Liquid cp approximation
        
        q_cond = h_desuper + h_fg_cond + h_subcool
        
        # Cooling capacity
        h_fg_evap = self.calculate_latent_heat(t_evap, refrigerant)
        h_superheat = props.specific_heat_vapor * superheat
        q_evap = h_fg_evap + h_superheat
        
        # COP calculations
        COP_heating = q_cond / h_comp if h_comp > 0 else 0
        COP_cooling = q_evap / h_comp if h_comp > 0 else 0
        
        # Apply system efficiencies
        COP_heating_real = COP_heating * self.mechanical_efficiency * self.heat_exchanger_effectiveness
        COP_cooling_real = COP_cooling * self.mechanical_efficiency * self.heat_exchanger_effectiveness
        
        # Carnot COP
        T_evap_K = t_evap + 273.15
        T_cond_K = t_cond + 273.15
        COP_carnot = T_cond_K / (T_cond_K - T_evap_K)
        
        # Volumetric efficiency estimation
        clearance_ratio = 0.05
        vol_eff = 1 - clearance_ratio * ((p_cond_in / p_evap_out) ** (1 / gamma) - 1)
        
        return {
            'cop_heating': COP_heating_real,
            'cop_cooling': COP_cooling_real,
            'cop_carnot': COP_carnot,
            'carnot_efficiency': COP_heating_real / COP_carnot,
            'pressure_ratio': p_cond_in / p_evap_out,
            'evaporator_pressure': p_evap,
            'condenser_pressure': p_cond,
            'discharge_temp': T2,
            'volumetric_efficiency': vol_eff,
            'compressor_work': h_comp,
            'heating_capacity': q_cond,
            'cooling_capacity': q_evap
        }
    
    def _calculate_cop_transcritical_co2(self, t_evap: float, t_gas_cooler: float,
                                         subcooling: float, superheat: float) -> Dict[str, float]:
        """Calculate transcritical CO2 cycle performance"""
        
        # Evaporator pressure (subcritical)
        p_evap = self.calculate_saturation_pressure(t_evap, Refrigerant.CO2)
        
        # Optimal gas cooler pressure correlation (Liao et al.)
        p_gc_opt = 2.778 * t_gas_cooler + 34.4  # bar
        p_gc = min(p_gc_opt, 120)  # Limit to typical maximum
        
        # Pressure ratio
        pressure_ratio = p_gc / p_evap
        
        # Discharge temperature estimation
        props = REFRIGERANT_PROPERTIES[Refrigerant.CO2]
        gamma = props.cp_cv_ratio
        n = 1 + (gamma - 1) / (gamma * self.compressor_efficiency)
        
        T1_K = t_evap + superheat + 273.15
        T2_K = T1_K * pressure_ratio ** ((n - 1) / n)
        T2 = T2_K - 273.15
        
        # Simplified COP correlation for transcritical CO2
        # Based on typical performance maps
        COP_base = 4.0 - 0.03 * (t_gas_cooler - t_evap)
        
        # Pressure ratio correction
        COP_heating = COP_base * (1 - 0.05 * math.log(pressure_ratio))
        
        # Apply efficiencies
        COP_heating_real = COP_heating * self.mechanical_efficiency * self.heat_exchanger_effectiveness
        COP_cooling_real = (COP_heating - 1) * self.mechanical_efficiency * self.heat_exchanger_effectiveness
        
        # Modified Carnot for transcritical
        T_evap_K = t_evap + 273.15
        T_m = (T2_K + t_gas_cooler + 273.15) / 2  # Mean heat rejection temperature
        COP_carnot_trans = T_m / (T_m - T_evap_K) * 0.6
        
        return {
            'cop_heating': COP_heating_real,
            'cop_cooling': COP_cooling_real,
            'cop_carnot': COP_carnot_trans,
            'carnot_efficiency': COP_heating_real / COP_carnot_trans,
            'pressure_ratio': pressure_ratio,
            'evaporator_pressure': p_evap,
            'gas_cooler_pressure': p_gc,
            'discharge_temp': T2,
            'operation_mode': 'Transcritical'
        }
    
    def calculate_system_performance(self, heat_source: HeatSource, refrigerant: Refrigerant,
                                   district_heating_supply_temp: float = 70,
                                   district_heating_return_temp: float = 40,
                                   ambient_temp: float = 10) -> Dict[str, any]:
        """Calculate complete system performance"""
        
        # Get heat source temperatures
        source_min, source_max = self.get_heat_source_temp(heat_source, ambient_temp)
        source_avg = (source_min + source_max) / 2
        
        # Set evaporator and condenser temperatures
        t_evap = source_avg - 7  # 7K approach
        t_cond = district_heating_supply_temp + 5  # 5K approach
        
        try:
            # Get refrigerant properties
            props = REFRIGERANT_PROPERTIES[refrigerant]
            
            # Calculate COP
            performance = self.calculate_cop_real(t_evap, t_cond, refrigerant)
            
            # Add system-level information
            performance.update({
                'heat_source': heat_source.value,
                'refrigerant': props.name,
                'source_temp_range': f"{source_min:.1f} - {source_max:.1f}°C",
                'evaporator_temp': t_evap,
                'condenser_temp': t_cond,
                'critical_temp': props.critical_temp,
                'dh_supply_temp': district_heating_supply_temp,
                'dh_return_temp': district_heating_return_temp,
                'temp_lift': t_cond - t_evap,
                'status': 'OK',
                'operation_mode': 'Transcritical' if t_cond >= props.critical_temp else 'Subcritical'
            })
            
        except Exception as e:
            performance = {
                'heat_source': heat_source.value,
                'refrigerant': REFRIGERANT_PROPERTIES[refrigerant].name,
                'status': 'ERROR',
                'error_message': str(e),
                'cop_heating': 0,
                'cop_carnot': 0
            }
        
        return performance


# Example usage
def main():
    calculator = HeatPumpCalculator()
    
    print("Heat Pump COP Calculator")
    print("=" * 80)
    print("Note: This calculator uses thermodynamic correlations for educational purposes.")
    print("For production use, consider using CoolProp or REFPROP for higher accuracy.")
    print("=" * 80)
    
    # Test configurations
    test_configs = [
        (HeatSource.AIR, Refrigerant.PROPANE, 70, 40, 5),
        (HeatSource.WASTEWATER, Refrigerant.AMMONIA, 70, 40, 10),
        (HeatSource.DATACENTER_WATER, Refrigerant.CO2, 70, 40, 15),
        (HeatSource.DATACENTER_WATER, Refrigerant.ISOBUTANE, 60, 35, 20),
        (HeatSource.WASTEWATER, Refrigerant.PROPYLENE, 80, 50, 15),
    ]
    
    for source, refrigerant, dh_supply, dh_return, ambient in test_configs:
        print(f"\n{'='*80}")
        print(f"Configuration:")
        print(f"  Heat Source: {source.value}")
        print(f"  Refrigerant: {refrigerant.name}")
        print(f"  District Heating: {dh_supply}/{dh_return}°C")
        print(f"  Ambient Temperature: {ambient}°C")
        
        result = calculator.calculate_system_performance(
            source, refrigerant, dh_supply, dh_return, ambient
        )
        
        if result['status'] == 'OK':
            print(f"\nOperating Conditions:")
            print(f"  Source Temperature Range: {result['source_temp_range']}")
            print(f"  Evaporator/Condenser Temp: {result['evaporator_temp']:.1f}/{result['condenser_temp']:.1f}°C")
            print(f"  Temperature Lift: {result['temp_lift']:.1f}K")
            print(f"  Operation Mode: {result['operation_mode']}")
            
            print(f"\nPressures:")
            print(f"  Evaporator Pressure: {result['evaporator_pressure']:.2f} bar")
            print(f"  Condenser Pressure: {result['condenser_pressure']:.2f} bar")
            print(f"  Pressure Ratio: {result['pressure_ratio']:.2f}")
            
            print(f"\nPerformance:")
            print(f"  COP Heating: {result['cop_heating']:.2f}")
            print(f"  COP Cooling: {result['cop_cooling']:.2f}")
            print(f"  COP Carnot: {result['cop_carnot']:.2f}")
            print(f"  Carnot Efficiency: {result['carnot_efficiency']:.1%}")
            
            print(f"\nAdditional Data:")
            print(f"  Discharge Temperature: {result['discharge_temp']:.1f}°C")
            if 'volumetric_efficiency' in result:
                print(f"  Volumetric Efficiency: {result['volumetric_efficiency']:.1%}")
        else:
            print(f"\nError: {result['error_message']}")


if __name__ == "__main__":
    main()
