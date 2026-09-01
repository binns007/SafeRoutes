from django.db import models


class Route(models.Model):
    """A planned journey between two districts, with a safety buffer."""
 
    source = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="routes_from")
    destination = models.ForeignKey("core.District", on_delete=models.CASCADE, related_name="routes_to")
    waypoints = models.JSONField(help_text="List of [lat, lon] points describing the planned path")
    safety_buffer_km = models.FloatField(default=2.5, help_text="1.96x CI buffer radius around the route")
    min_safety_score_crossed = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
 
    def __str__(self):
        return f"Route {self.source.name} -> {self.destination.name} (#{self.pk})"
 
 
class GPSPing(models.Model):
    """A single location update along a route (Stage 5: live monitoring)."""
 
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="pings")
    sequence = models.PositiveIntegerField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    nearest_district = models.ForeignKey(
        "core.District", null=True, blank=True, on_delete=models.SET_NULL
    )
    safety_score_at_point = models.FloatField(null=True, blank=True)
    in_unsafe_zone = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        ordering = ["route", "sequence"]
 
    def __str__(self):
        return f"Ping #{self.sequence} on route {self.route_id}"
 
 
class Alert(models.Model):
    """
    Raised when a GPS ping shows a deviation into an unsafe zone.
 
    This alert is shown to the user only, as an in-app popup with action
    choices (reroute / continue / dismiss) -- SafeRoutes does not notify
    any third party (emergency contacts, authorities, etc.) on the user's
    behalf. See dashboard's alert modal (route_detail.js).
    """
 
    SEVERITY_CHOICES = [("warning", "Warning"), ("critical", "Critical")]
    RESPONSE_CHOICES = [
        ("rerouted", "User chose: reroute me"),
        ("continued", "User chose: I'm okay, continue"),
        ("dismissed", "User dismissed the alert"),
    ]
 
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="alerts")
    ping = models.ForeignKey(GPSPing, on_delete=models.CASCADE, related_name="alerts")
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="warning")
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)
    acknowledged = models.BooleanField(
        default=False, help_text="User has seen/actioned the popup for this alert."
    )
    user_response = models.CharField(
        max_length=20, choices=RESPONSE_CHOICES, blank=True,
        help_text="Which popup action the user chose, if any.",
    )
 
    class Meta:
        ordering = ["-created_at"]
 
    def __str__(self):
        return f"[{self.severity}] {self.message}"
 