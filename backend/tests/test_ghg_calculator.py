import pytest

from carbon.ghg_calculator import GHGCalculator
from carbon.verra_constants import (
    CHARGER_EFFICIENCY,
    EF_DIESEL_KG_PER_L,
    EF_GRID_KENYA_KG_PER_KWH,
    EF_PETROL_KG_PER_L,
    NET_VCU_FACTOR,
    VEHICLE_PARAMS,
    WTT_DIESEL,
    WTT_PETROL,
    VehicleCategory,
)


@pytest.mark.parametrize(
    ("vehicle_category", "distance_km", "charger_type"),
    [
        (VehicleCategory.E_BIKE, 10.0, "L1"),
        (VehicleCategory.PSV_PASSENGER_CAR, 12.0, "L2"),
        (VehicleCategory.TRANSIT_BUS, 20.0, "DCFC"),
    ],
)
def test_calculate_trip_matches_vm0038_hand_calculation(vehicle_category, distance_km, charger_type):
    params = VEHICLE_PARAMS[vehicle_category]
    fuel_ef = EF_PETROL_KG_PER_L if params.fuel_type == "petrol" else EF_DIESEL_KG_PER_L
    wtt = WTT_PETROL if params.fuel_type == "petrol" else WTT_DIESEL
    baseline_kg = round(distance_km * params.afec_l_per_km * fuel_ef * wtt, 4)
    electricity_kwh = distance_km * params.ev_kwh_per_km
    pe_kg = round((electricity_kwh / CHARGER_EFFICIENCY[charger_type]) * EF_GRID_KENYA_KG_PER_KWH, 4)
    gross_kg = round(max(baseline_kg - pe_kg, 0.0), 4)
    expected_net_vcu = round((gross_kg / 1000.0) * NET_VCU_FACTOR, 8)

    result = GHGCalculator.calculate_trip(vehicle_category, distance_km, charger_type)

    assert result.vehicle_category == vehicle_category
    assert result.baseline_emissions_kg == pytest.approx(baseline_kg, abs=1e-4)
    assert result.project_emissions_kg == pytest.approx(pe_kg, abs=1e-4)
    assert result.gross_reduction_kg == pytest.approx(gross_kg, abs=1e-4)
    assert result.net_vcu == pytest.approx(expected_net_vcu, abs=1e-7)
    assert result.gross_reduction_kg >= 0
    assert result.net_reduction_kg > 0
