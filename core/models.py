from django.db import models


class District(models.Model):
    """
    Raw + engineered record for one administrative district, as pulled from
    the (simulated) Open Government Data Platform pipeline.

    Fields map directly to the parameters named in the SafeRoutes proposal:
    crime rate, police presence, population, literacy, per-capita
    expenditure and forest cover.
    """

    name = models.CharField(max_length=120, unique=True)
    state = models.CharField(max_length=120, default="Kerala")
    latitude = models.FloatField()
    longitude = models.FloatField()

    # --- raw ingested fields (Stage 1: Data Ingestion) ---
    population = models.PositiveIntegerField(help_text="District population")
    literacy_rate = models.FloatField(help_text="Percent, 0-100")
    police_strength = models.PositiveIntegerField(help_text="Sanctioned police personnel")
    per_capita_expenditure = models.FloatField(help_text="Annual government spend per capita, INR")
    forest_cover_pct = models.FloatField(help_text="Percent of district area under forest cover")

    crime_rape = models.PositiveIntegerField(default=0, help_text="Reported cases / year")
    crime_kidnapping = models.PositiveIntegerField(default=0, help_text="Reported cases / year")
    crime_other_ipc_women = models.PositiveIntegerField(
        default=0, help_text="Other IPC crimes against women, reported cases / year"
    )

    # --- engineered fields (Stage 2: Pre-processing / feature engineering) ---
    crime_rate_per_100k = models.FloatField(null=True, blank=True)
    police_per_100k = models.FloatField(null=True, blank=True)
    literacy_disparity = models.FloatField(
        null=True, blank=True, help_text="Absolute gap vs. state literacy benchmark"
    )
    population_growth_rate = models.FloatField(null=True, blank=True, help_text="Percent, synthetic")

    data_source = models.CharField(
        max_length=200, default="Synthetic (Open Government Data Platform format)"
    )
    last_ingested_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name}, {self.state}"

    @property
    def total_crimes_against_women(self):
        return self.crime_rape + self.crime_kidnapping + self.crime_other_ipc_women

    def compute_engineered_fields(self, state_avg_literacy=None):
        """Stage 2 pre-processing: derive rate-based features from raw counts."""
        if self.population:
            self.crime_rate_per_100k = round(
                self.total_crimes_against_women / self.population * 100_000, 3
            )
            self.police_per_100k = round(self.police_strength / self.population * 100_000, 3)
        if state_avg_literacy is not None:
            self.literacy_disparity = round(abs(self.literacy_rate - state_avg_literacy), 3)
