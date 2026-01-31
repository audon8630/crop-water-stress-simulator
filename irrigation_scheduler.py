import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Tuple, Dict
import json
import argparse


@dataclass
class SoilParameters:
    """Soil hydraulic parameters"""
    field_capacity: float = 0.30  # volumetric water content at field capacity
    wilting_point: float = 0.12   # volumetric water content at wilting point
    saturation: float = 0.45      # volumetric water content at saturation
    depth: float = 600            # root zone depth in mm
    infiltration_rate: float = 50  # mm/day
    drainage_coeff: float = 0.15   # drainage coefficient

@dataclass
class CropParameters:
    """Crop-specific parameters"""
    name: str = "Tomato"
    kc_initial: float = 0.6   # crop coefficient - initial stage
    kc_mid: float = 1.15      # crop coefficient - mid season
    kc_end: float = 0.8       # crop coefficient - end season
    stage_days: List[int] = None  # days for each growth stage
    stress_threshold: float = 0.5  # MAD - Management Allowed Depletion (0-1)
    
    def __post_init__(self):
        if self.stage_days is None:
            self.stage_days = [25, 40, 45, 20]  # initial, development, mid, late

class SoilMoistureModel:
    """1D Soil moisture bucket model"""
    
    def __init__(self, soil: SoilParameters, crop: CropParameters):
        self.soil = soil
        self.crop = crop
        self.theta = soil.field_capacity  # initial moisture content
        self.history = []
        
    def calculate_taw(self) -> float:
        """Total Available Water (mm)"""
        return (self.soil.field_capacity - self.soil.wilting_point) * self.soil.depth
    
    def calculate_raw(self) -> float:
        """Readily Available Water (mm) - water before stress occurs"""
        return self.calculate_taw() * self.crop.stress_threshold
    
    def get_current_depletion(self) -> float:
        """Current soil water depletion (mm)"""
        return (self.soil.field_capacity - self.theta) * self.soil.depth
    
    def get_stress_level(self) -> float:
        """Crop stress level (0=no stress, 1=wilting point)"""
        depletion = self.get_current_depletion()
        raw = self.calculate_raw()
        if depletion <= raw:
            return 0.0
        else:
            taw = self.calculate_taw()
            return min((depletion - raw) / (taw - raw), 1.0)
    
    def update(self, precip: float, et0: float, irrigation: float, kc: float) -> Dict:
        """
        Update soil moisture for one day
        
        Args:
            precip: precipitation (mm)
            et0: reference evapotranspiration (mm)
            irrigation: irrigation applied (mm)
            kc: crop coefficient
        
        Returns:
            dict with water balance components
        """
        # 1. Crop ET
        etc = et0 * kc
        
        # 2. Water input
        total_input = precip + irrigation
        
        # 3. Infiltration (limited by infiltration rate)
        infiltration = min(total_input, self.soil.infiltration_rate)
        runoff = max(0, total_input - infiltration)
        
        # 4. Update moisture by infiltration
        theta_new = self.theta + infiltration / self.soil.depth
        
        # 5. Evapotranspiration (limited by available water)
        max_et = max(0, (theta_new - self.soil.wilting_point) * self.soil.depth)
        actual_et = min(etc, max_et)
        theta_new -= actual_et / self.soil.depth
        
        # 6. Drainage (when above field capacity)
        drainage = 0.0
        if theta_new > self.soil.field_capacity:
            excess = (theta_new - self.soil.field_capacity) * self.soil.depth
            drainage = excess * self.soil.drainage_coeff
            theta_new -= drainage / self.soil.depth
        
        # 7. Constrain between wilting point and saturation
        theta_new = np.clip(theta_new, self.soil.wilting_point, self.soil.saturation)
        
        # 8. Update model state BEFORE computing stress
        self.theta = theta_new
        
        depletion = (self.soil.field_capacity - theta_new) * self.soil.depth
        stress = self.get_stress_level()
        
        # 9. Store results
        result = {
            'theta': theta_new,
            'precipitation': precip,
            'irrigation': irrigation,
            'infiltration': infiltration,
            'runoff': runoff,
            'etc': etc,
            'actual_et': actual_et,
            'drainage': drainage,
            'depletion': depletion,
            'stress': stress
        }
        
        self.history.append(result)
        return result

class IrrigationScheduler:
    """Adaptive irrigation scheduler"""
    
    def __init__(self, model: SoilMoistureModel, forecast_days: int = 7):
        self.model = model
        self.forecast_days = forecast_days
        self.irrigation_efficiency = 0.85  # irrigation system efficiency
        
    def rule_based_decision(self, weather_forecast: pd.DataFrame, 
                           current_day: int) -> Tuple[float, str]:
        """
        Rule-based irrigation decision
        
        Returns:
            (irrigation_amount, reason)
        """
        depletion = self.model.get_current_depletion()
        raw = self.model.calculate_raw()
        taw = self.model.calculate_taw()
        stress = self.model.get_stress_level()
        
        # Get forecast for next few days
        forecast = weather_forecast.iloc[current_day:current_day+self.forecast_days]
        total_precip_forecast = forecast['precipitation'].sum()
        total_et_forecast = forecast['et0'].sum() * forecast['kc'].iloc[0]
        
        # Expected depletion without irrigation
        expected_depletion = depletion + total_et_forecast - total_precip_forecast
        
        # Decision rules
        if stress > 0.1:
            # Critical stress - irrigate immediately to field capacity
            amount = depletion / self.irrigation_efficiency
            return amount, "Critical stress detected"
        
        elif depletion >= raw * 0.9:
            # Near stress threshold - irrigate to field capacity
            amount = depletion / self.irrigation_efficiency
            return amount, "Approaching stress threshold"
        
        elif expected_depletion > raw and total_precip_forecast < 5:
            # Forecast shows stress likely, minimal rain expected
            # Irrigate partially to avoid stress
            amount = (expected_depletion - raw * 0.7) / self.irrigation_efficiency
            amount = max(0, amount)
            if amount > 5:  # minimum irrigation event
                return amount, "Preventive irrigation based on forecast"
        
        return 0.0, "No irrigation needed"
    
    def optimize_irrigation(self, weather_forecast: pd.DataFrame,
                           current_day: int, horizon: int = 7) -> float:
        """
        Simple optimization: find minimum irrigation to avoid stress over horizon
        
        Returns:
            optimal irrigation amount (mm)
        """
        # Simulate forward without irrigation
        test_model = SoilMoistureModel(self.model.soil, self.model.crop)
        test_model.theta = self.model.theta
        
        max_stress = 0
        for i in range(horizon):
            day_idx = current_day + i
            if day_idx >= len(weather_forecast):
                break
            
            row = weather_forecast.iloc[day_idx]
            test_model.update(row['precipitation'], row['et0'], 0, row['kc'])
            max_stress = max(max_stress, test_model.get_stress_level())
        
        # If stress occurs, calculate irrigation needed
        if max_stress > 0.05:
            # Binary search for minimum irrigation
            low, high = 0, self.model.calculate_taw() * 1.5
            tolerance = 0.5
            
            while high - low > tolerance:
                mid = (low + high) / 2
                
                # Test this irrigation amount
                test_model = SoilMoistureModel(self.model.soil, self.model.crop)
                test_model.theta = self.model.theta
                test_model.update(0, 0, mid, 1.0)  # Apply irrigation
                
                # Simulate forward
                max_test_stress = 0
                for i in range(horizon):
                    day_idx = current_day + i
                    if day_idx >= len(weather_forecast):
                        break
                    row = weather_forecast.iloc[day_idx]
                    test_model.update(row['precipitation'], row['et0'], 0, row['kc'])
                    max_test_stress = max(max_test_stress, test_model.get_stress_level())
                
                if max_test_stress > 0.05:
                    low = mid
                else:
                    high = mid
            
            return high / self.irrigation_efficiency
        
        return 0.0

def generate_weather_forecast(days: int, start_date: datetime) -> pd.DataFrame:
    """Generate synthetic weather forecast"""
    np.random.seed(42)
    
    dates = [start_date + timedelta(days=i) for i in range(days)]
    
    # Seasonal pattern for ET0
    day_of_year = np.array([d.timetuple().tm_yday for d in dates])
    base_et0 = 4 + 2 * np.sin(2 * np.pi * (day_of_year - 80) / 365)
    
    # Add random variation
    et0 = base_et0 + np.random.normal(0, 0.5, days)
    et0 = np.clip(et0, 2, 8)
    
    # Precipitation (sporadic events)
    precip = np.zeros(days)
    rain_days = np.random.choice(days, size=days//7, replace=False)
    precip[rain_days] = np.random.exponential(15, len(rain_days))
    
    return pd.DataFrame({
        'date': dates,
        'et0': et0,
        'precipitation': precip
    })

def get_crop_coefficient(day: int, crop: CropParameters) -> float:
    """Get crop coefficient based on growth stage"""
    cumulative_days = np.cumsum(crop.stage_days)
    
    if day < cumulative_days[0]:
        return crop.kc_initial
    elif day < cumulative_days[1]:
        # Linear interpolation during development
        days_in_stage = day - cumulative_days[0]
        stage_length = crop.stage_days[1]
        return crop.kc_initial + (crop.kc_mid - crop.kc_initial) * days_in_stage / stage_length
    elif day < cumulative_days[2]:
        return crop.kc_mid
    elif day < cumulative_days[3]:
        # Linear interpolation during late season
        days_in_stage = day - cumulative_days[2]
        stage_length = crop.stage_days[3]
        return crop.kc_mid + (crop.kc_end - crop.kc_mid) * days_in_stage / stage_length
    else:
        return crop.kc_end

def run_simulation(simulation_days: int = 120, 
                   scheduler_type: str = "rule_based") -> Tuple[pd.DataFrame, Dict]:
    """
    Run irrigation simulation
    
    Args:
        simulation_days: number of days to simulate
        scheduler_type: "rule_based" or "optimized"
    
    Returns:
        (results_df, statistics)
    """
    # Initialize
    soil = SoilParameters()
    crop = CropParameters()
    model = SoilMoistureModel(soil, crop)
    scheduler = IrrigationScheduler(model)
    
    # Generate weather
    start_date = datetime(2024, 4, 1)  # Start of growing season
    weather = generate_weather_forecast(simulation_days, start_date)
    
    # Add crop coefficient to weather
    weather['kc'] = [get_crop_coefficient(i, crop) for i in range(simulation_days)]
    
    # Simulation
    results = []
    total_irrigation = 0
    irrigation_events = 0
    
    for day in range(simulation_days):
        # Make irrigation decision
        if scheduler_type == "rule_based":
            irrigation, reason = scheduler.rule_based_decision(weather, day)
        else:
            irrigation = scheduler.optimize_irrigation(weather, day)
            reason = "Optimized" if irrigation > 0 else "No irrigation needed"
        
        if irrigation > 0:
            total_irrigation += irrigation
            irrigation_events += 1
        
        # Update model
        result = model.update(
            precip=weather.iloc[day]['precipitation'],
            et0=weather.iloc[day]['et0'],
            irrigation=irrigation,
            kc=weather.iloc[day]['kc']
        )
        
        result['date'] = weather.iloc[day]['date']
        result['day'] = day
        result['kc'] = weather.iloc[day]['kc']
        result['decision_reason'] = reason
        results.append(result)
    
    # Create results dataframe
    results_df = pd.DataFrame(results)
    
    # Calculate statistics
    stats = {
        'total_irrigation': total_irrigation,
        'irrigation_events': irrigation_events,
        'avg_irrigation_per_event': total_irrigation / max(irrigation_events, 1),
        'total_precipitation': weather['precipitation'].sum(),
        'total_etc': results_df['etc'].sum(),
        'total_actual_et': results_df['actual_et'].sum(),
        'max_stress': results_df['stress'].max(),
        'avg_stress': results_df['stress'].mean(),
        'days_with_stress': (results_df['stress'] > 0.1).sum(),
        'water_use_efficiency': results_df['actual_et'].sum() / (total_irrigation + weather['precipitation'].sum())
    }
    
    return results_df, stats

def create_visualizations(results_df: pd.DataFrame, stats: Dict, output_file: str):
    """Create comprehensive visualization dashboard"""
    fig = plt.figure(figsize=(16, 12))
    gs = fig.add_gridspec(4, 2, hspace=0.3, wspace=0.3)
    
    # 1. Soil Moisture Evolution
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(results_df['day'], results_df['theta'], 'b-', linewidth=2, label='Soil Moisture')
    ax1.axhline(y=0.30, color='g', linestyle='--', label='Field Capacity')
    ax1.axhline(y=0.12, color='r', linestyle='--', label='Wilting Point')
    ax1.axhline(y=0.21, color='orange', linestyle=':', label='Stress Threshold')
    ax1.set_xlabel('Day', fontsize=10)
    ax1.set_ylabel('Volumetric Water Content', fontsize=10)
    ax1.set_title('Soil Moisture Dynamics', fontsize=12, fontweight='bold')
    ax1.legend(loc='best')
    ax1.grid(True, alpha=0.3)
    
    # 2. Water Balance Components
    ax2 = fig.add_subplot(gs[1, :])
    ax2.bar(results_df['day'], results_df['precipitation'], 
            label='Precipitation', alpha=0.7, color='skyblue')
    ax2.bar(results_df['day'], results_df['irrigation'], 
            label='Irrigation', alpha=0.7, color='green')
    ax2.plot(results_df['day'], results_df['etc'], 
             'r-', linewidth=1.5, label='Crop ET', alpha=0.7)
    ax2.set_xlabel('Day', fontsize=10)
    ax2.set_ylabel('Water (mm)', fontsize=10)
    ax2.set_title('Water Balance Components', fontsize=12, fontweight='bold')
    ax2.legend(loc='best')
    ax2.grid(True, alpha=0.3)
    
    # 3. Crop Stress Level
    ax3 = fig.add_subplot(gs[2, 0])
    ax3.fill_between(results_df['day'], results_df['stress'], 
                     alpha=0.6, color='red', label='Stress Level')
    ax3.axhline(y=0.1, color='orange', linestyle='--', 
                label='Acceptable Stress Limit')
    ax3.set_xlabel('Day', fontsize=10)
    ax3.set_ylabel('Stress Level (0-1)', fontsize=10)
    ax3.set_title('Crop Water Stress', fontsize=12, fontweight='bold')
    ax3.legend(loc='best')
    ax3.grid(True, alpha=0.3)
    ax3.set_ylim([0, 1])
    
    # 4. Crop Coefficient Evolution
    ax4 = fig.add_subplot(gs[2, 1])
    ax4.plot(results_df['day'], results_df['kc'], 'g-', linewidth=2)
    ax4.set_xlabel('Day', fontsize=10)
    ax4.set_ylabel('Crop Coefficient (Kc)', fontsize=10)
    ax4.set_title('Crop Development Stage', fontsize=12, fontweight='bold')
    ax4.grid(True, alpha=0.3)
    ax4.set_ylim([0, 1.5])
    
    # 5. Irrigation Events
    ax5 = fig.add_subplot(gs[3, 0])
    irrigation_days = results_df[results_df['irrigation'] > 0]
    ax5.bar(irrigation_days['day'], irrigation_days['irrigation'], 
            color='blue', alpha=0.7)
    ax5.set_xlabel('Day', fontsize=10)
    ax5.set_ylabel('Irrigation Amount (mm)', fontsize=10)
    ax5.set_title(f'Irrigation Events (Total: {stats["irrigation_events"]})', 
                  fontsize=12, fontweight='bold')
    ax5.grid(True, alpha=0.3)
    
    # 6. Statistics Summary
    ax6 = fig.add_subplot(gs[3, 1])
    ax6.axis('off')
    
    stats_text = f"""
    SIMULATION STATISTICS
    ═══════════════════════════════
    
    Water Use:
    • Total Irrigation: {stats['total_irrigation']:.1f} mm
    • Irrigation Events: {stats['irrigation_events']}
    • Avg per Event: {stats['avg_irrigation_per_event']:.1f} mm
    • Total Precipitation: {stats['total_precipitation']:.1f} mm
    
    Crop Performance:
    • Total Crop ET: {stats['total_etc']:.1f} mm
    • Actual ET: {stats['total_actual_et']:.1f} mm
    • Water Use Efficiency: {stats['water_use_efficiency']:.2f}
    
    Stress Metrics:
    • Max Stress: {stats['max_stress']:.3f}
    • Avg Stress: {stats['avg_stress']:.3f}
    • Days with Stress: {stats['days_with_stress']}
    """
    
    ax6.text(0.1, 0.5, stats_text, fontsize=9, family='monospace',
             verticalalignment='center', bbox=dict(boxstyle='round', 
             facecolor='wheat', alpha=0.3))
    
    plt.suptitle('Adaptive Irrigation Scheduler - Field Scale Simulation', 
                 fontsize=14, fontweight='bold', y=0.995)
    
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"✓ Visualization saved to {output_file}")
    
    return fig

def save_irrigation_schedule(results_df: pd.DataFrame, output_file: str):
    """Save irrigation schedule to CSV"""
    schedule = results_df[results_df['irrigation'] > 0][
        ['date', 'day', 'irrigation', 'depletion', 'stress', 'decision_reason']
    ].copy()
    
    schedule['date'] = schedule['date'].dt.strftime('%Y-%m-%d')
    schedule.columns = ['Date', 'Day', 'Irrigation (mm)', 
                       'Soil Depletion (mm)', 'Stress Level', 'Reason']
    
    schedule.to_csv(output_file, index=False)
    print(f"✓ Irrigation schedule saved to {output_file}")

def main(scheduler_type: str = "rule_based"):
    print("=" * 60)
    print("CROP WATER STRESS SIMULATION & ADAPTIVE IRRIGATION SCHEDULER")
    print("=" * 60)
    print()
    
    # Run simulation with selected scheduler
    pretty_name = scheduler_type.replace("_", " ").title()
    print(f"Running simulation with {pretty_name} Scheduler...")
    results_main, stats_main = run_simulation(120, scheduler_type)
    
    # Create visualizations
    print("\nGenerating visualizations...")
    create_visualizations(results_main, stats_main, 'irrigation_dashboard.png')
    
    # Save irrigation schedule
    save_irrigation_schedule(results_main, 'irrigation_schedule.csv')
    
    # Print summary
    print("\n" + "=" * 60)
    print("SIMULATION SUMMARY")
    print("=" * 60)
    for key, value in stats_main.items():
        print(f"{key:.<40} {value:.2f}")
    
    print("\n" + "=" * 60)
    print("✓ Simulation complete!")
    print("=" * 60)
    
    # Compare with the other scheduler for reference
    other_type = "optimized" if scheduler_type == "rule_based" else "rule_based"
    other_pretty = other_type.replace("_", " ").title()
    
    print(f"\n\nRunning comparison with {other_pretty} Scheduler...")
    results_other, stats_other = run_simulation(120, other_type)
    
    print("\nCOMPARISON:")
    print(f"  {pretty_name} Total Irrigation: {stats_main['total_irrigation']:.1f} mm")
    print(f"  {other_pretty} Total Irrigation:  {stats_other['total_irrigation']:.1f} mm")
    print(f"  Water Savings (using {other_pretty} instead of {pretty_name}): "
          f"{stats_main['total_irrigation'] - stats_other['total_irrigation']:.1f} mm "
          f"({100*(stats_main['total_irrigation'] - stats_other['total_irrigation'])/stats_main['total_irrigation']:.1f}%)")
    
    return results_main, stats_main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crop Water Stress Simulation & Adaptive Irrigation Scheduler"
    )
    parser.add_argument(
        "--scheduler",
        choices=["rule_based", "optimized"],
        default="rule_based",
        help="Choose irrigation scheduler type (default: rule_based)"
    )
    
    args = parser.parse_args()
    
    results, stats = main(scheduler_type=args.scheduler)
