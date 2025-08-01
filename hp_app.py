import CoolProp.CoolProp as CP
from CoolProp.CoolProp import PropsSI
import numpy as np
from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from enum import Enum

class Refrigerant(Enum):
    """Supported refrigerants with CoolProp names"""
    PROPANE = "Propane"  # R290
    ISOBUTANE = "IsoButane"  # R600a
    PROPYLENE = "Propylene"  # R1270
    AMMONIA = "Ammonia"  # R717
    CO2 = "CarbonDioxide"  # R744

class HeatSource(Enum):
    """Available heat sources"""
    AIR = "Air"
    WASTEWATER = "Wastewater"
    DATACENTER_WATER = "Datacenter Water"

class HeatPumpCalculator:
    def __init__(self):
        self.compressor_efficiency = 0.75  # Isentropic efficiency
        self.mechanical_efficiency = 0.95  # Mechanical/electrical efficiency
        self.heat_exchanger_effectiveness = 0.85  # Heat exchanger effectiveness
        self.pressure_drop_ratio = 0.02  # 2% pressure drop in heat exchangers
        
    def get_heat_source_temp(self, source: HeatSource, ambient_temp: float = 10.0) -> Tuple[float, float]:
        """
        Get typical temperature range for heat sources
        Returns: (min_temp, max_temp) in °C
        """
        if source == HeatSource.AIR:
            return (ambient_temp - 5, ambient_temp)
        elif source == HeatSource.WASTEWATER:
            return (10, 20)
        elif source == HeatSource.DATACENTER_WATER:
            return (20, 35)
    
    def calculate_cop_real(self, t_evap: float, t_cond: float, refrigerant: Refrigerant,
                          subcooling: float = 5, superheat: float = 5) -> Dict[str, float]:
        """
        Calculate real COP using CoolProp for accurate refrigerant properties
        
        Parameters:
        t_evap: Evaporator temperature in °C
        t_cond: Condenser temperature in °C
        refrigerant: Refrigerant type
        subcooling: Subcooling in K
        superheat: Superheat in K
        
        Returns: Dictionary with COP and other performance parameters
        """
        fluid = refrigerant.value
        
        # Convert temperatures to Kelvin
        T_evap = t_evap + 273.15
        T_cond = t_cond + 273.15
        
        try:
            # Get critical properties
            T_crit = PropsSI('Tcrit', fluid)
            P_crit = PropsSI('Pcrit', fluid)
            
            # Check for transcritical operation
            if T_cond >= T_crit:
                if refrigerant == Refrigerant.CO2:
                    return self._calculate_cop_transcritical_co2(
                        t_evap, t_cond, subcooling, superheat
                    )
                else:
                    raise ValueError(f"Condenser temperature {t_cond}°C exceeds critical "
                                   f"temperature {T_crit-273.15:.1f}°C for {refrigerant.name}")
            
            # Get saturation pressures
            P_evap = PropsSI('P', 'T', T_evap, 'Q', 1, fluid)
            P_cond = PropsSI('P', 'T', T_cond, 'Q', 1, fluid)
            
            # Apply pressure drops
            P_evap_out = P_evap * (1 - self.pressure_drop_ratio)
            P_cond_in = P_cond * (1 + self.pressure_drop_ratio)
            
            # State points for simple vapor compression cycle
            # State 1: Compressor inlet (superheated vapor)
            T1 = T_evap + superheat
            h1 = PropsSI('H', 'T', T1, 'P', P_evap_out, fluid)
            s1 = PropsSI('S', 'T', T1, 'P', P_evap_out, fluid)
            
            # State 2s: Isentropic compression endpoint
            h2s = PropsSI('H', 'S', s1, 'P', P_cond_in, fluid)
            T2s = PropsSI('T', 'S', s1, 'P', P_cond_in, fluid)
            
            # State 2: Actual compression endpoint
            h2 = h1 + (h2s - h1) / self.compressor_efficiency
            T2 = PropsSI('T', 'H', h2, 'P', P_cond_in, fluid)
            
            # State 3: Condenser outlet (subcooled liquid)
            T3 = T_cond - subcooling
            h3 = PropsSI('H', 'T', T3, 'P', P_cond, fluid)
            
            # State 4: After expansion valve (two-phase)
            h4 = h3  # Isenthalpic expansion
            T4 = PropsSI('T', 'H', h4, 'P', P_evap, fluid)
            x4 = PropsSI('Q', 'H', h4, 'P', P_evap, fluid)  # Vapor quality
            
            # Performance calculations
            w_comp = (h2 - h1) / 1000  # kJ/kg
            q_cond = (h2 - h3) / 1000  # kJ/kg
            q_evap = (h1 - h4) / 1000  # kJ/kg
            
            # COP calculation
            COP_cooling = q_evap / w_comp
            COP_heating = q_cond / w_comp
            
            # Apply mechanical and heat exchanger efficiencies
            COP_heating_real = COP_heating * self.mechanical_efficiency * self.heat_exchanger_effectiveness
            
            # Carnot COP for reference
            COP_carnot = T_cond / (T_cond - T_evap)
            
            # Volumetric heating capacity (kW/m³)
            v1 = 1 / PropsSI('D', 'T', T1, 'P', P_evap_out, fluid)  # Specific volume
            VHC = q_cond / v1  # kJ/m³
            
            return {
                'cop_heating': COP_heating_real,
                'cop_cooling': COP_cooling * self.mechanical_efficiency * self.heat_exchanger_effectiveness,
                'cop_carnot': COP_carnot,
                'carnot_efficiency': COP_heating_real / COP_carnot,
                'pressure_ratio': P_cond_in / P_evap_out,
                'evaporator_pressure': P_evap / 1e5,  # Convert to bar
                'condenser_pressure': P_cond / 1e5,  # Convert to bar
                'discharge_temp': T2 - 273.15,  # Convert to °C
                'compressor_work': w_comp,
                'heating_capacity': q_cond,
                'cooling_capacity': q_evap,
                'vapor_quality_after_expansion': x4,
                'volumetric_heating_capacity': VHC / 1000  # MW/m³
            }
            
        except Exception as e:
            raise ValueError(f"CoolProp calculation error: {str(e)}")
    
    def _calculate_cop_transcritical_co2(self, t_evap: float, t_gas_cooler: float,
                                         subcooling: float, superheat: float) -> Dict[str, float]:
        """
        Calculate transcritical CO2 cycle performance using CoolProp
        """
        fluid = "CarbonDioxide"
        T_evap = t_evap + 273.15
        T_gc_out = t_gas_cooler + 273.15
        
        # Evaporator pressure (subcritical)
        P_evap = PropsSI('P', 'T', T_evap, 'Q', 1, fluid)
        
        # Optimal gas cooler pressure for transcritical CO2
        # Correlation from Liao et al. (2000)
        P_gc_opt = 2.778e5 * (T_gc_out - 273.15) + 3.44e6  # Pa
        P_gc = min(P_gc_opt, 12e6)  # Limit to 120 bar
        
        # State 1: Compressor inlet
        T1 = T_evap + superheat
        h1 = PropsSI('H', 'T', T1, 'P', P_evap, fluid)
        s1 = PropsSI('S', 'T', T1, 'P', P_evap, fluid)
        
        # State 2s: Isentropic compression
        h2s = PropsSI('H', 'S', s1, 'P', P_gc, fluid)
        
        # State 2: Actual compression
        h2 = h1 + (h2s - h1) / self.compressor_efficiency
        T2 = PropsSI('T', 'H', h2, 'P', P_gc, fluid)
        
        # State 3: Gas cooler outlet
        h3 = PropsSI('H', 'T', T_gc_out, 'P', P_gc, fluid)
        
        # State 4: After expansion
        h4 = h3
        T4 = PropsSI('T', 'H', h4, 'P', P_evap, fluid)
        x4 = PropsSI('Q', 'H', h4, 'P', P_evap, fluid)
        
        # Performance
        w_comp = (h2 - h1) / 1000  # kJ/kg
        q_gc = (h2 - h3) / 1000  # kJ/kg
        q_evap = (h1 - h4) / 1000  # kJ/kg
        
        COP_heating = q_gc / w_comp
        COP_heating_real = COP_heating * self.mechanical_efficiency * self.heat_exchanger_effectiveness
        
        # Modified Carnot COP for transcritical
        T_m = (T2 + T_gc_out) / 2  # Mean heat rejection temperature
        COP_carnot_trans = T_m / (T_m - T_evap)
        
        return {
            'cop_heating': COP_heating_real,
            'cop_cooling': (q_evap / w_comp) * self.mechanical_efficiency * self.heat_exchanger_effectiveness,
            'cop_carnot': COP_carnot_trans,
            'carnot_efficiency': COP_heating_real / COP_carnot_trans,
            'pressure_ratio': P_gc / P_evap,
            'evaporator_pressure': P_evap / 1e5,
            'gas_cooler_pressure': P_gc / 1e5,
            'discharge_temp': T2 - 273.15,
            'compressor_work': w_comp,
            'heating_capacity': q_gc,
            'cooling_capacity': q_evap,
            'vapor_quality_after_expansion': x4,
            'operation_mode': 'Transcritical'
        }
    
    def calculate_system_performance(self, heat_source: HeatSource, refrigerant: Refrigerant,
                                   district_heating_supply_temp: float = 70,
                                   district_heating_return_temp: float = 40,
                                   ambient_temp: float = 10) -> Dict[str, any]:
        """
        Calculate complete system performance
        """
        # Get heat source temperatures
        source_min, source_max = self.get_heat_source_temp(heat_source, ambient_temp)
        source_avg = (source_min + source_max) / 2
        
        # Set evaporator temperature (5-10K approach)
        t_evap = source_avg - 7
        
        # Set condenser temperature (5-10K approach)
        t_cond = district_heating_supply_temp + 5
        
        try:
            # Get refrigerant critical temperature
            T_crit = PropsSI('Tcrit', refrigerant.value) - 273.15
            
            # Calculate COP
            performance = self.calculate_cop_real(t_evap, t_cond, refrigerant)
            
            # Add system-level information
            performance.update({
                'heat_source': heat_source.value,
                'refrigerant': f"{refrigerant.name} ({refrigerant.value})",
                'source_temp_range': f"{source_min:.1f} - {source_max:.1f}°C",
                'evaporator_temp': t_evap,
                'condenser_temp': t_cond,
                'critical_temp': T_crit,
                'dh_supply_temp': district_heating_supply_temp,
                'dh_return_temp': district_heating_return_temp,
                'temp_lift': t_cond - t_evap,
                'status': 'OK',
                'operation_mode': 'Transcritical' if t_cond >= T_crit else 'Subcritical'
            })
            
        except Exception as e:
            performance = {
                'heat_source': heat_source.value,
                'refrigerant': f"{refrigerant.name} ({refrigerant.value})",
                'status': 'ERROR',
                'error_message': str(e),
                'cop_heating': 0,
                'cop_carnot': 0
            }
        
        return performance


# Example usage
def main():
    calculator = HeatPumpCalculator()
    
    print("Heat Pump COP Calculator with CoolProp")
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
            print(f"  COP Heating (Real): {result['cop_heating']:.2f}")
            print(f"  COP Cooling (Real): {result['cop_cooling']:.2f}")
            print(f"  COP Carnot: {result['cop_carnot']:.2f}")
            print(f"  Carnot Efficiency: {result['carnot_efficiency']:.1%}")
            
            print(f"\nThermodynamic Properties:")
            print(f"  Discharge Temperature: {result['discharge_temp']:.1f}°C")
            print(f"  Compressor Work: {result['compressor_work']:.1f} kJ/kg")
            print(f"  Heating Capacity: {result['heating_capacity']:.1f} kJ/kg")
            print(f"  Vapor Quality after Expansion: {result['vapor_quality_after_expansion']:.2f}")
            
            if 'volumetric_heating_capacity' in result:
                print(f"  Volumetric Heating Capacity: {result['volumetric_heating_capacity']:.3f} MW/m³")
        else:
            print(f"\nError: {result['error_message']}")


if __name__ == "__main__":
    main()
