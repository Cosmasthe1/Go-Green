"""
uber_green — Go Green × Uber Guest Rides API integration
"""
from .adapter import UberGreenAdapter, RideOffer, DataSource
from .auth    import token_manager, UberAuthError, UberCredentialsMissing
from .client  import uber_client, UberAPIError, UberRateLimitError
from .models  import (
    Location, EstimatesResponse, ProductEstimate,
    Fare, Trip, TripDetail, GuestInfo, CreateTripRequest,
)

__all__ = [
    "UberGreenAdapter",
    "RideOffer",
    "DataSource",
    "token_manager",
    "uber_client",
    "UberAuthError",
    "UberCredentialsMissing",
    "UberAPIError",
    "UberRateLimitError",
    "Location",
    "EstimatesResponse",
    "ProductEstimate",
    "Fare",
    "Trip",
    "TripDetail",
    "GuestInfo",
    "CreateTripRequest",
]
