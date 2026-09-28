import pytest

from carbon.ghg_calculator import GHGCalculator
from carbon.verra_constants import VehicleCategory


@pytest.mark.parametrize(
    ("vehicle_category", "distance_km", "charger_type", "expected_net_vcu"),
    [
        (VehicleCategory.E_BIKE, 10.0, "L1", 0.00073353),
        (VehicleCategory.PSV_PASSENGER_CAR, 12.0, "L2", 0.01144114),
        (VehicleCategory.TRANSIT_BUS, 20.0, "DCFC", 0.24869313),
    ],
)
def test_calculate_trip_matches_vm0038_hand_calculation(vehicle_category, distance_km, charger_type, expected_net_vcu):
    result = GHGCalculator.calculate_trip(vehicle_category, distance_km, charger_type)

    assert result.vehicle_category == vehicle_category
    assert result.net_vcu == pytest.approx(expected_net_vcu, rel=1e-6)
    assert result.gross_reduction_kg >= 0
    assert result.net_reduction_kg > 0
