"""
Stage 5: Maps & Cab Integration.

Route planning is intentionally simplified for this demo -- it interpolates
a straight-line path between source and destination district centers rather
than calling a real road-routing engine, then layers the safety-cluster
output on top to (a) report how safe the planned path is and (b) simulate
GPS pings, flagging any deviation into an unsafe zone. Swap `plan_route`
for a call to Google Maps Directions API / OSRM to get real road geometry
without changing anything downstream.
"""
import math
import random

from core.models import District
from clustering.models import DistrictClusterAssignment
from .models import Route, GPSPing, Alert

UNSAFE_TIERS = {"III", "IV"}
WAYPOINT_COUNT = 12
CONFIDENCE_MULTIPLIER = 1.96  # matches the 1.96x CI buffer named in the proposal
BASE_BUFFER_KM = 1.3


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def nearest_district(lat, lon, exclude_ids=None):
    best, best_dist = None, float("inf")
    qs = District.objects.all()
    if exclude_ids:
        qs = qs.exclude(id__in=exclude_ids)
    for d in qs:
        dist = haversine_km(lat, lon, d.latitude, d.longitude)
        if dist < best_dist:
            best, best_dist = d, dist
    return best, best_dist


def _district_safety(district):
    try:
        assignment = district.cluster_assignment
        return assignment.safety_score, assignment.cluster.tier
    except DistrictClusterAssignment.DoesNotExist:
        return None, None


def plan_route(source: District, destination: District) -> Route:
    lats = [source.latitude + (destination.latitude - source.latitude) * t / (WAYPOINT_COUNT - 1)
            for t in range(WAYPOINT_COUNT)]
    lons = [source.longitude + (destination.longitude - source.longitude) * t / (WAYPOINT_COUNT - 1)
            for t in range(WAYPOINT_COUNT)]
    waypoints = list(zip(lats, lons))

    min_score = None
    for lat, lon in waypoints:
        d, _ = nearest_district(lat, lon)
        score, _tier = _district_safety(d)
        if score is not None:
            min_score = score if min_score is None else min(min_score, score)

    buffer_km = round(CONFIDENCE_MULTIPLIER * BASE_BUFFER_KM, 2)
    return Route.objects.create(
        source=source,
        destination=destination,
        waypoints=[[lat, lon] for lat, lon in waypoints],
        safety_buffer_km=buffer_km,
        min_safety_score_crossed=round(min_score, 2) if min_score is not None else None,
    )


def simulate_journey(route: Route, inject_deviation: bool = True):
    """
    Walk the planned waypoints, generating a GPS ping at each. If
    `inject_deviation` is True, one midpoint is nudged toward the nearest
    high-risk district center, simulating a vehicle going off-route --
    this is what should trigger a real-time alert.
    """
    route.pings.all().delete()
    route.alerts.all().delete()

    waypoints = list(route.waypoints)
    deviate_index = len(waypoints) // 2 if inject_deviation else None

    pings, alerts = [], []
    for i, (lat, lon) in enumerate(waypoints):
        actual_lat, actual_lon = lat, lon

        if inject_deviation and i == deviate_index:
            # find the closest Tier III/IV district and pull the vehicle
            # toward it, simulating a driver going off the recommended path
            nearby_unsafe, nearby_unsafe_dist = None, float("inf")
            for d in District.objects.all():
                _, dtier = _district_safety(d)
                if dtier in UNSAFE_TIERS:
                    dist = haversine_km(lat, lon, d.latitude, d.longitude)
                    if dist < nearby_unsafe_dist:
                        nearby_unsafe, nearby_unsafe_dist = d, dist
            if nearby_unsafe:
                pull = 0.65
                actual_lat = lat + (nearby_unsafe.latitude - lat) * pull
                actual_lon = lon + (nearby_unsafe.longitude - lon) * pull

        nearest, dist_km = nearest_district(actual_lat, actual_lon)
        score, tier = _district_safety(nearest)
        deviation_km = haversine_km(actual_lat, actual_lon, lat, lon)
        in_unsafe = bool(tier in UNSAFE_TIERS and deviation_km > route.safety_buffer_km)

        ping = GPSPing.objects.create(
            route=route,
            sequence=i,
            latitude=round(actual_lat, 6),
            longitude=round(actual_lon, 6),
            nearest_district=nearest,
            safety_score_at_point=score,
            in_unsafe_zone=in_unsafe,
        )
        pings.append(ping)

        if in_unsafe:
            alert = Alert.objects.create(
                route=route,
                ping=ping,
                severity="critical" if (score or 100) < 35 else "warning",
                message=(
                    f"Route deviation detected near {nearest.name}: "
                    f"{deviation_km:.1f} km off planned path, inside a "
                    f"Tier {tier} zone (safety score {score:.0f}/100)."
                ),
            )
            alerts.append(alert)

    return pings, alerts
