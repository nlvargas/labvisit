import logging
import math
from dataclasses import dataclass

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0


def distance_km(lat1, lng1, lat2, lng2):
    """Straight-line distance between two points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def visit_fee(lab, km):
    """Returns the home visit fee rounded up to $500, or None when the address is out of range."""
    if km is None:
        return lab.visit_base_fee_clp
    if km > lab.max_visit_km:
        return None
    fee = lab.visit_base_fee_clp + lab.visit_fee_per_km_clp * km
    return int(math.ceil(fee / 500) * 500)


@dataclass
class Place:
    latitude: float
    longitude: float
    address: str
    place_id: str


def geocode(query, lab):
    """Finds a typed address near the lab with Places API (New). Returns None when not found or not configured."""
    key = settings.GOOGLE_MAPS_SERVER_KEY
    if not key:
        return None
    body = {"textQuery": query, "regionCode": "cl", "languageCode": "es", "pageSize": 1}
    if lab.latitude is not None:
        body["locationBias"] = {"circle": {"center": {"latitude": lab.latitude, "longitude": lab.longitude},
                                           "radius": 50000.0}}
    try:
        response = httpx.post(
            "https://places.googleapis.com/v1/places:searchText",
            json=body,
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": "places.id,places.formattedAddress,places.location"},
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Geocoding failed: %s", exc)
        return None
    places = response.json().get("places") or []
    if not places:
        return None
    place = places[0]
    return Place(place["location"]["latitude"], place["location"]["longitude"],
                 place.get("formattedAddress", ""), place.get("id", ""))
