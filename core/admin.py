from django.contrib import admin
from .models import District


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = (
        "name", "state", "population", "literacy_rate", "police_strength",
        "crime_rate_per_100k", "police_per_100k", "last_ingested_at",
    )
    list_filter = ("state",)
    search_fields = ("name",)
    readonly_fields = ("last_ingested_at",)
    fieldsets = (
        ("Identity", {"fields": ("name", "state", "latitude", "longitude")}),
        ("Raw ingested data (Stage 1)", {
            "fields": (
                "population", "literacy_rate", "police_strength",
                "per_capita_expenditure", "forest_cover_pct",
                "crime_rape", "crime_kidnapping", "crime_other_ipc_women",
            )
        }),
        ("Engineered features (Stage 2)", {
            "fields": (
                "crime_rate_per_100k", "police_per_100k",
                "literacy_disparity", "population_growth_rate",
            )
        }),
        ("Provenance", {"fields": ("data_source", "last_ingested_at")}),
    )
