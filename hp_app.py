import math
import numpy as np
from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from enum import Enum

class Refrigerant(Enum):
    """Supported refrigerants with their properties"""
    PROPANE = "R290"  # Hydrocarbon
    ISOBUTANE = "R600a"  # Hydrocarbon
    PROPYLENE = "R1270"  # Hydrocarbon
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
    # Antoine equation coefficients for vapor pressure
    antoine_a: float
    antoine_b: float
    antoine_c: float

# Refrigerant properties database
REFRIGERANT_PROPERTIES = {
    Refrigerant.PROPANE: RefrigerantProperties(
        name="Propane (R290)",
        critical_temp=96.74,
        critical_pressure=42.51,
        boiling_point=-42.1,
        antoine_a=15.726,
        antoine_b=1872.46,
        antoine_c=-25.16
    ),
    Refrigerant.ISOBUTANE: RefrigerantProperties(
        name="Isobutane (R600a)",
        critical_temp=134.66,
        critical_pressure=36.40,
        boiling_point=-11.7,
        antoine_a=15.854,
        antoine_b=2348.67,
        antoine_c=-27.85
    ),
    Refrigerant.PROPYLENE: RefrigerantProperties(
        name="Propylene (R1270)",
        critical_temp=91.06,
        critical_pressure=45.55,
        boiling_point=-47.6,
        antoine_a=15.7027,
        antoine_b=1807.53,
        antoine_c=-26.15
    ),
    Refrigerant.AMMONIA: RefrigerantProperties(
        name="Ammonia (R717)",
        critical_temp=132.25,
        critical_pressure=113.33,
        boiling_point=-33.34,
        antoine_a=16.9481,
        antoine_b=2132.50,
        antoine_c=-32.98
    ),
    Refrigerant.CO2: RefrigerantProperties(
        name="Carbon Dioxide (R744)",
        critical_temp=31.06,
        critical_pressure=73.77,
        boiling_point=-78.46,  # Sublimation point at 1 atm
        antoine_a=22.5898,
        antoine_b=3103.39,
        antoine_c=-0.16
    )
}

class HeatPumpCalculator:
    def __init__(self):
        self.compressor_efficiency = 0.75  # Typical isentropic efficiency
        self.mechanical_efficiency = 0.95  # Mechanical/electrical efficiency
        self.heat_exchanger_effectiveness = 0.85  # Heat exchanger effectiveness
        
    def get_heat_source_temp(self, source: HeatSource, ambient_temp: float = 10.0) -> Tuple[float, float]:
        """
        Get typical temperature range for heat sources
        Returns: (min_temp, max_temp) in °C
        """
        if source == HeatSource.AIR:
            # Air temperature varies with ambient
            return (ambient_temp - 5, ambient_temp)
        elif source == HeatSource.WASTEWATER:
            # Wastewater typically 10-20°C
            return (10, 20)
        elif source == HeatSource.DATACENTER_WATER:
            # Datacenter cooling water typically 20-35°C
            return (20, 35)
    
    def calculate_saturation_pressure(self, temp: float, refrigerant: Refrigerant) -> float:
        """
        Calculate saturation pressure using Antoine equation
        temp: Temperature in °C
        Returns: Pressure in bar
        """
        props = REFRIGERANT_PROPERTIES[refrigerant]
        
        # For CO2 near critical point, use different correlation
        if refrigerant == Refrigerant.CO2 and temp > 25:
            # Simplified correlation for CO2 near critical point
            return 73.77 * (1 - (31.06 - temp) / 31.06) ** 2
        
        # Antoine equation: log10(P) = A - B/(C + T)
        # Where P is in mmHg and T is in °C
        log_p_mmhg = props.antoine_a - props.antoine_b / (props.antoine_c + temp)
        p_mmhg = math.pow(10, log_p_mmhg)  # Use math.pow instead of **
        p_bar = p_mmhg * 0.00133322  # Convert mmHg to bar
        
        return p_bar
    
    def calculate_cop_carnot(self, t_evap: float, t_cond: float) -> float:
        """
        Calculate ideal Carnot COP
        t_evap: Evaporator temperature in °C
        t_cond: Condenser temperature in °C
        Returns: Carnot COP
        """
        t_evap_k = t_evap + 273.15
        t_cond_k = t_cond + 273.15
        
        cop_carnot = t_cond_k / (t_cond_k - t_evap_k)
        return cop_carnot
    
    def calculate_cop_real(self, t_evap: float, t_cond: float, refrigerant: Refrigerant,
                          subcooling: float = 5, superheat: float = 5) -> Dict[str, float]:
        """
        Calculate real COP considering refrigerant properties and inefficiencies
        
        Parameters:
        t_evap: Evaporator temperature in °C
        t_cond: Condenser temperature in °C
        refrigerant: Refrigerant type
        subcooling: Subcooling in K
        superheat: Superheat in K
        
        Returns: Dictionary with COP and other performance parameters
        """
        # Check if operating conditions are feasible
        props = REFRIGERANT_PROPERTIES[refrigerant]
        if t_cond >= props.critical_temp:
            # Transcritical operation for CO2
            if refrigerant == Refrigerant.CO2:
                return self._calculate_cop_transcritical_co2(t_evap, t_cond, subcooling, superheat)
            else:
                raise ValueError(f"Condenser temperature {t_cond}°C exceeds critical temperature "
                               f"{props.critical_temp}°C for {props.name}")
        
        # Calculate pressures
        p_evap = self.calculate_saturation_pressure(t_evap, refrigerant)
        p_cond = self.calculate_saturation_pressure(t_cond, refrigerant)
        
        # Pressure ratio
        pressure_ratio = p_cond / p_evap
        
        # Estimate compressor work (simplified)
        # Using polytropic compression with typical exponent
        n = 1.2  # Polytropic exponent
        t_evap_k = t_evap + 273.15
        t_discharge_k = t_evap_k * (pressure_ratio ** ((n - 1) / n))
        
        # Specific work (normalized)
        w_comp = (t_discharge_k - t_evap_k) / self.compressor_efficiency
        
        # Heat rejected (normalized)
        q_cond = t_discharge_k - (t_cond + 273.15) + (t_cond - t_evap)
        
        # COP calculation
        cop_real = q_cond / w_comp * self.mechanical_efficiency * self.heat_exchanger_effectiveness
        
        # Carnot COP for reference
        cop_carnot = self.calculate_cop_carnot(t_evap, t_cond)
        
        # Carnot efficiency
        carnot_efficiency = cop_real / cop_carnot
        
        return {
            'cop_real': cop_real,
            'cop_carnot': cop_carnot,
            'carnot_efficiency': carnot_efficiency,
            'pressure_ratio': pressure_ratio,
            'evaporator_pressure': p_evap,
            'condenser_pressure': p_cond,
            'discharge_temp': t_discharge_k - 273.15
        }
    
    def _calculate_cop_transcritical_co2(self, t_evap: float, t_gas_cooler: float,
                                         subcooling: float, superheat: float) -> Dict[str, float]:
        """
        Special calculation for transcritical CO2 cycle
        """
        # Evaporator pressure (subcritical)
        p_evap = self.calculate_saturation_pressure(t_evap, Refrigerant.CO2)
        
        # Gas cooler pressure (transcritical) - optimized for COP
        # Typical correlation for optimal high pressure
        p_opt = 2.778 * t_gas_cooler + 34.4  # bar
        p_gas_cooler = min(p_opt, 120)  # Limit to typical maximum
        
        # Pressure ratio
        pressure_ratio = p_gas_cooler / p_evap
        
        # Simplified transcritical COP correlation
        # Based on typical CO2 heat pump performance
        cop_base = 4.5 - 0.04 * (t_gas_cooler - t_evap)
        
        # Adjust for pressure ratio
        cop_real = cop_base * (1 - 0.1 * math.log(pressure_ratio))
        
        # Apply efficiencies
        cop_real *= self.mechanical_efficiency * self.heat_exchanger_effectiveness
        
        # Theoretical maximum (modified Carnot for transcritical)
        t_evap_k = t_evap + 273.15
        t_gas_k = t_gas_cooler + 273.15
        cop_carnot = t_gas_k / (t_gas_k - t_evap_k) * 0.6  # Reduced due to transcritical
        
        return {
            'cop_real': cop_real,
            'cop_carnot': cop_carnot,
            'carnot_efficiency': cop_real / cop_carnot if cop_carnot > 0 else 0,
            'pressure_ratio': pressure_ratio,
            'evaporator_pressure': p_evap,
            'gas_cooler_pressure': p_gas_cooler,
            'discharge_temp': t_gas_cooler + 20  # Approximate
        }
    
    def calculate_system_performance(self, heat_source: HeatSource, refrigerant: Refrigerant,
                                   district_heating_supply_temp: float = 70,
                                   district_heating_return_temp: float = 40,
                                   ambient_temp: float = 10) -> Dict[str, any]:
        """
        Calculate complete system performance
        
        Parameters:
        heat_source: Type of heat source
        refrigerant: Refrigerant type
        district_heating_supply_temp: DH supply temperature in °C
        district_heating_return_temp: DH return temperature in °C
        ambient_temp: Ambient temperature in °C
        
        Returns: Complete performance analysis
        """
        # Get heat source temperatures
        source_min, source_max = self.get_heat_source_temp(heat_source, ambient_temp)
        source_avg = (source_min + source_max) / 2
        
        # Set evaporator temperature (typically 5-10K below source)
        t_evap = source_avg - 7
        
        # Set condenser temperature (typically 5-10K above sink)
        t_cond = district_heating_supply_temp + 5
        
        try:
            # Calculate COP
            performance = self.calculate_cop_real(t_evap, t_cond, refrigerant)
            
            # Add system-level information
            performance.update({
                'heat_source': heat_source.value,
                'refrigerant': REFRIGERANT_PROPERTIES[refrigerant].name,
                'source_temp_range': f"{source_min:.1f} - {source_max:.1f}°C",
                'evaporator_temp': t_evap,
                'condenser_temp': t_cond,
                'dh_supply_temp': district_heating_supply_temp,
                'dh_return_temp': district_heating_return_temp,
                'temp_lift': t_cond - t_evap,
                'status': 'OK'
            })
            
        except ValueError as e:
            # Handle infeasible conditions
            performance = {
                'heat_source': heat_source.value,
                'refrigerant': REFRIGERANT_PROPERTIES[refrigerant].name,
                'status': 'ERROR',
                'error_message': str(e),
                'cop_real': 0,
                'cop_carnot': 0
            }
        
        return performance


# Example usage and testing
def main():
    calculator = HeatPumpCalculator()
    
    print("Heat Pump COP Calculator")
    print("=" * 60)
    
    # Test different configurations
    test_configs = [
        (HeatSource.AIR, Refrigerant.PROPANE, 70, 40, 5),
        (HeatSource.WASTEWATER, Refrigerant.AMMONIA, 70, 40, 10),
        (HeatSource.DATACENTER_WATER, Refrigerant.CO2, 70, 40, 15),
        (HeatSource.DATACENTER_WATER, Refrigerant.ISOBUTANE, 60, 35, 20),
        (HeatSource.WASTEWATER, Refrigerant.PROPYLENE, 80, 50, 15),
    ]
    
    for source, refrigerant, dh_supply, dh_return, ambient in test_configs:
        print(f"\nConfiguration:")
        print(f"  Heat Source: {source.value}")
        print(f"  Refrigerant: {refrigerant.value}")
        print(f"  District Heating: {dh_supply}/{dh_return}°C")
        print(f"  Ambient Temperature: {ambient}°C")
        
        result = calculator.calculate_system_performance(
            source, refrigerant, dh_supply, dh_return, ambient
        )
        
        if result['status'] == 'OK':
            print(f"\nResults:")
            print(f"  Source Temperature Range: {result['source_temp_range']}")
            print(f"  Evaporator/Condenser Temp: {result['evaporator_temp']:.1f}/{result['condenser_temp']:.1f}°C")
            print(f"  Temperature Lift: {result['temp_lift']:.1f}K")
            print(f"  Pressure Ratio: {result['pressure_ratio']:.2f}")
            print(f"  COP (Real): {result['cop_real']:.2f}")
            print(f"  COP (Carnot): {result['cop_carnot']:.2f}")
            print(f"  Carnot Efficiency: {result['carnot_efficiency']:.1%}")
        else:
            print(f"\nError: {result['error_message']}")
        
        print("-" * 60)


if __name__ == "__main__":
    main()
