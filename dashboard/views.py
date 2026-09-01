import json

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseNotAllowed
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.models import District
from clustering.models import SafetyCluster, DistrictClusterAssignment
from tracking.models import Route, Alert
from tracking.services import plan_route, simulate_journey


def home(request):
    clusters = SafetyCluster.objects.filter(algorithm="kmeans").order_by("-avg_safety_score")
    districts = District.objects.select_related("cluster_assignment__cluster").order_by("name")
    recent_alerts = Alert.objects.select_related("route", "ping")[:5]
    return render(request, "dashboard/home.html", {
        "clusters": clusters,
        "districts": districts,
        "recent_alerts": recent_alerts,
        "has_data": districts.exists(),
        "has_clusters": clusters.exists(),
    })


def heatmap(request):
    return render(request, "dashboard/heatmap.html", {
        "has_clusters": SafetyCluster.objects.filter(algorithm="kmeans").exists(),
    })


def route_planner(request):
    districts = District.objects.order_by("name")
    if request.method == "POST":
        source = get_object_or_404(District, pk=request.POST.get("source"))
        destination = get_object_or_404(District, pk=request.POST.get("destination"))
        if source.pk == destination.pk:
            return render(request, "dashboard/route_planner.html", {
                "districts": districts,
                "error": "Source and destination must be different districts.",
            })
        route = plan_route(source, destination)
        inject = request.POST.get("simulate_deviation") == "on"
        simulate_journey(route, inject_deviation=inject)
        return redirect(reverse("dashboard:route_detail", args=[route.pk]))

    return render(request, "dashboard/route_planner.html", {"districts": districts})


def route_detail(request, route_id):
    route = get_object_or_404(Route, pk=route_id)
    return render(request, "dashboard/route_detail.html", {
        "route": route,
        "alerts": route.alerts.all(),
    })


def alerts_list(request):
    alerts = Alert.objects.select_related("route", "route__source", "route__destination", "ping")
    return render(request, "dashboard/alerts.html", {"alerts": alerts})


# ---------- JSON endpoints consumed by the map JS ----------

def api_clusters(request):
    data = []
    for assignment in DistrictClusterAssignment.objects.select_related("district", "cluster"):
        d = assignment.district
        data.append({
            "id": d.id,
            "name": d.name,
            "lat": d.latitude,
            "lon": d.longitude,
            "safety_score": assignment.safety_score,
            "tier": assignment.cluster.tier,
            "tier_label": assignment.cluster.get_tier_display(),
            "color": assignment.cluster.color_hex,
            "crime_rate_per_100k": d.crime_rate_per_100k,
            "police_per_100k": d.police_per_100k,
            "literacy_rate": d.literacy_rate,
        })
    return JsonResponse({"districts": data})


def api_route_data(request, route_id):
    route = get_object_or_404(Route, pk=route_id)
    pings = [{
        "sequence": p.sequence,
        "lat": p.latitude,
        "lon": p.longitude,
        "in_unsafe_zone": p.in_unsafe_zone,
        "safety_score": p.safety_score_at_point,
        "nearest_district": p.nearest_district.name if p.nearest_district else None,
    } for p in route.pings.all()]
    alerts = [{
        "id": a.id,
        "sequence": a.ping.sequence,
        "severity": a.severity,
        "message": a.message,
        "acknowledged": a.acknowledged,
    } for a in route.alerts.select_related("ping").all()]
    return JsonResponse({
        "source": route.source.name,
        "destination": route.destination.name,
        "waypoints": route.waypoints,
        "safety_buffer_km": route.safety_buffer_km,
        "min_safety_score_crossed": route.min_safety_score_crossed,
        "pings": pings,
        "alerts": alerts,
    })


@require_POST
def api_route_reroute(request, route_id):
    """
    "Reroute me" popup action. Re-simulates the journey with no injected
    deviation, i.e. snaps the vehicle back onto the safe planned path.
    Any alerts from the previous (deviated) run are cleared along with it,
    since simulate_journey() wipes and regenerates pings/alerts for the route.
    """
    route = get_object_or_404(Route, pk=route_id)
    simulate_journey(route, inject_deviation=False)
    return JsonResponse({"status": "rerouted"})


@require_POST
def api_route_acknowledge(request, route_id):
    """
    "I'm okay, continue" / "Dismiss" popup actions. Marks the route's
    currently-unresolved alerts as acknowledged by the user, recording which
    choice they made, so the popup doesn't reappear for the same alerts.
    Does NOT notify anyone else -- this only updates local alert state.
    """
    route = get_object_or_404(Route, pk=route_id)
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        payload = {}
    choice = payload.get("choice")
    if choice not in {"continued", "dismissed"}:
        return JsonResponse({"error": "invalid choice"}, status=400)

    updated = route.alerts.filter(acknowledged=False).update(
        acknowledged=True,
        user_response=choice,
        resolved=(choice == "continued"),
    )
    return JsonResponse({"status": "ok", "updated": updated})