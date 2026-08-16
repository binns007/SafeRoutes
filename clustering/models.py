from django.db import models


class BenchmarkCity(models.Model):
    """
    Dummy benchmark data from globally recognized safe cities, used as the
    baseline every district cluster is scored against (Stage 4: Safety
    Scoring). Figures are illustrative reference values for demonstration,
    not sourced from a live feed.
    """
    name = models.CharField(max_length=120)
    country = models.CharField(max_length=120)
    crime_rate_per_100k = models.FloatField()
    police_per_100k = models.FloatField()
    literacy_rate = models.FloatField()
    reference_safety_score = models.FloatField(help_text="0-100, benchmark ceiling")

    class Meta:
        verbose_name_plural = "Benchmark cities"

    def __str__(self):
        return f"{self.name}, {self.country}"


class SafetyCluster(models.Model):
    """One cluster produced by the clustering model, with its safety tier."""

    TIER_CHOICES = [
        ("I", "Tier I - Benchmark Safe"),
        ("II", "Tier II - Moderate"),
        ("III", "Tier III - Elevated Risk"),
        ("IV", "Tier IV - High Risk"),
    ]

    algorithm = models.CharField(max_length=20, choices=[("kmeans", "K-Means"), ("gmm", "Gaussian Mixture")])
    cluster_index = models.IntegerField(help_text="Raw label id output by the model, e.g. 0-3")
    tier = models.CharField(max_length=4, choices=TIER_CHOICES)
    color_hex = models.CharField(max_length=7, default="#35C4A1")
    avg_safety_score = models.FloatField(help_text="0-100, higher = safer")
    district_count = models.PositiveIntegerField(default=0)
    silhouette_score = models.FloatField(null=True, blank=True)
    trained_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-avg_safety_score"]

    def __str__(self):
        return f"[{self.algorithm}] Cluster {self.cluster_index} - {self.get_tier_display()}"


class DistrictClusterAssignment(models.Model):
    """Links a District to the SafetyCluster it was placed in, with its own score."""

    district = models.OneToOneField(
        "core.District", on_delete=models.CASCADE, related_name="cluster_assignment"
    )
    cluster = models.ForeignKey(SafetyCluster, on_delete=models.CASCADE, related_name="districts")
    safety_score = models.FloatField(help_text="0-100, higher = safer")
    assigned_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.district.name} -> {self.cluster}"
