"""
uber_green/models.py — Go Green
────────────────────────────────────────────────────────────────────────────
Typed request/response models for the Uber Guest Rides API.

All field names mirror the official Uber API schema exactly so JSON
serialisation/deserialisation is a 1-to-1 mapping with no name translation.

References:
  POST /v1/guests/trips/estimates
  POST /v1/guests/trips
  GET  /v1/guests/trips/{request_id}
  GET  /v1/guests/trips/{request_id}/status
────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Shared sub-objects
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Location:
    """Pickup or dropoff location."""
    latitude:  float
    longitude: float
    address:   Optional[str] = None    # human-readable — improves dispatcher accuracy

    def to_dict(self) -> dict:
        d: dict = {"latitude": self.latitude, "longitude": self.longitude}
        if self.address:
            d["address"] = self.address
        return d


@dataclass
class FareBreakdownItem:
    name:  str
    type:  str
    value: float


@dataclass
class Fare:
    """Upfront fare returned in estimates / trip detail."""
    currency_code:  str
    value:          float          # total fare
    display:        str            # e.g. "$11.96"
    fare_id:        str            # use when creating a trip to lock in price
    expires_at:     Optional[int] = None    # Unix timestamp
    low_estimate:   Optional[float] = None
    high_estimate:  Optional[float] = None
    fare_breakdown: list[FareBreakdownItem] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Fare":
        breakdown = [
            FareBreakdownItem(
                name  = item.get("name", ""),
                type  = item.get("type", ""),
                value = float(item.get("value", 0)),
            )
            for item in d.get("fare_breakdown", [])
        ]
        return cls(
            currency_code  = d.get("currency_code", "USD"),
            value          = float(d.get("value", 0)),
            display        = d.get("display", ""),
            fare_id        = d.get("fare_id", ""),
            expires_at     = d.get("expires_at"),
            low_estimate   = d.get("low_estimate"),
            high_estimate  = d.get("high_estimate"),
            fare_breakdown = breakdown,
        )


@dataclass
class Trip:
    """Trip geometry returned in estimates."""
    distance_estimate:        float   # in distance_unit
    duration_estimate:        int     # seconds
    distance_unit:            str     # "mile" | "km"
    travel_distance_estimate: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Trip":
        return cls(
            distance_estimate        = float(d.get("distance_estimate", 0)),
            duration_estimate        = int(d.get("duration_estimate", 0)),
            distance_unit            = d.get("distance_unit", "km"),
            travel_distance_estimate = d.get("travel_distance_estimate"),
        )


@dataclass
class ReserveInfo:
    """Uber Reserve / scheduled ride availability info."""
    availability_predictor: Optional[str] = None   # "GREEN" | "YELLOW" | "RED" | "UNKNOWN"
    block_type:             Optional[str] = None   # "BLOCK" | "WARN" | "NONE"


# ─────────────────────────────────────────────────────────────────────────────
# Estimates response
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ProductEstimate:
    """
    One product returned by POST /v1/guests/trips/estimates.
    Represents a single ride type (e.g. UberX, Uber Green, Comfort Electric).
    """
    product_id:      str
    display_name:    str            # e.g. "Uber Green"
    short_desc:      str            # e.g. "Electric vehicle"
    fare:            Optional[Fare] = None
    pickup_estimate: Optional[int]  = None    # ETA in minutes
    trip:            Optional[Trip] = None
    reserve_info:    Optional[ReserveInfo] = None
    image_url:       Optional[str] = None
    capacity:        Optional[int] = None    # max passengers

    # Derived helpers
    @property
    def is_green(self) -> bool:
        """Heuristic: is this product an EV/electric/green option?"""
        kw = {"green", "electric", "ev", "comfort electric", "black ev", "eco"}
        name_lower = self.display_name.lower()
        desc_lower = self.short_desc.lower()
        return any(k in name_lower or k in desc_lower for k in kw)

    @classmethod
    def from_dict(cls, d: dict) -> "ProductEstimate":
        product = d.get("product", {})
        estimate_info = d.get("estimate_info", {})

        fare_data = estimate_info.get("fare")
        fare = Fare.from_dict(fare_data) if fare_data else None

        trip_data = estimate_info.get("trip")
        trip = Trip.from_dict(trip_data) if trip_data else None

        ri = d.get("reserve_info", {})
        fi = ri.get("fulfillment_indicators", {})
        rb = fi.get("request_blocker", {})
        ap = fi.get("availability_predictor", {})

        return cls(
            product_id      = product.get("product_id", ""),
            display_name    = product.get("display_name", ""),
            short_desc      = product.get("short_description", ""),
            fare            = fare,
            pickup_estimate = estimate_info.get("pickup_estimate"),
            trip            = trip,
            image_url       = product.get("image", {}).get("url"),
            capacity        = product.get("capacity"),
            reserve_info    = ReserveInfo(
                availability_predictor = ap.get("predictor_result"),
                block_type             = rb.get("block_type"),
            ) if fi else None,
        )


@dataclass
class EstimatesResponse:
    """Full response from POST /v1/guests/trips/estimates."""
    product_estimates: list[ProductEstimate]
    etas_unavailable:  bool = False
    fares_unavailable: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "EstimatesResponse":
        raw_estimates = d.get("product_estimates", [])
        return cls(
            product_estimates = [ProductEstimate.from_dict(e) for e in raw_estimates],
            etas_unavailable  = d.get("etas_unavailable", False),
            fares_unavailable = d.get("fares_unavailable", False),
        )

    def green_products(self) -> list[ProductEstimate]:
        """Filter to EV / electric / green products only."""
        return [p for p in self.product_estimates if p.is_green]


# ─────────────────────────────────────────────────────────────────────────────
# Trip creation request
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class GuestInfo:
    """Rider identity for trip creation."""
    first_name:   str
    last_name:    str
    phone_number: str   # E.164 format e.g. +254712345678
    email:        Optional[str] = None

    def to_dict(self) -> dict:
        d: dict = {
            "first_name":   self.first_name,
            "last_name":    self.last_name,
            "phone_number": self.phone_number,
        }
        if self.email:
            d["email"] = self.email
        return d


@dataclass
class CreateTripRequest:
    """
    Request body for POST /v1/guests/trips  (on-demand ride creation).
    fare_id locks in the upfront price from the estimates call.
    """
    guest:      GuestInfo
    pickup:     Location
    dropoff:    Location
    product_id: str
    fare_id:    Optional[str] = None   # from estimates — locks upfront fare

    def to_dict(self) -> dict:
        d: dict = {
            "guest":      self.guest.to_dict(),
            "pickup":     self.pickup.to_dict(),
            "dropoff":    self.dropoff.to_dict(),
            "product_id": self.product_id,
        }
        if self.fare_id:
            d["fare_id"] = self.fare_id
        return d


# ─────────────────────────────────────────────────────────────────────────────
# Trip status / detail
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DriverInfo:
    name:         Optional[str]   = None
    phone_number: Optional[str]   = None
    picture_url:  Optional[str]   = None
    rating:       Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "DriverInfo":
        return cls(
            name         = d.get("name"),
            phone_number = d.get("phone_number"),
            picture_url  = d.get("picture_url"),
            rating       = d.get("rating"),
        )


@dataclass
class VehicleInfo:
    make:          Optional[str] = None
    model:         Optional[str] = None
    license_plate: Optional[str] = None
    picture_url:   Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "VehicleInfo":
        return cls(
            make          = d.get("make"),
            model         = d.get("model"),
            license_plate = d.get("license_plate"),
            picture_url   = d.get("picture_url"),
        )


@dataclass
class TripDetail:
    """Full trip object from GET /v1/guests/trips/{request_id}."""
    request_id:  str
    status:      str           # "processing"|"accepted"|"arriving"|"in_progress"|"completed"|"cancelled"
    driver:      Optional[DriverInfo]  = None
    vehicle:     Optional[VehicleInfo] = None
    eta:         Optional[int]         = None    # minutes until pickup
    fare:        Optional[Fare]        = None
    raw:         Any                   = field(default=None, repr=False)

    @classmethod
    def from_dict(cls, d: dict) -> "TripDetail":
        driver  = DriverInfo.from_dict(d["driver"])   if d.get("driver")  else None
        vehicle = VehicleInfo.from_dict(d["vehicle"]) if d.get("vehicle") else None
        fare    = Fare.from_dict(d["fare"])           if d.get("fare")    else None
        return cls(
            request_id = d.get("request_id", ""),
            status     = d.get("status", ""),
            driver     = driver,
            vehicle    = vehicle,
            eta        = d.get("eta"),
            fare       = fare,
            raw        = d,
        )
