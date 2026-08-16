"""
Stage 1: Data Ingestion (simulated).

Populates the database with district-level records shaped like the real
Open Government Data Platform fields named in the proposal (population,
literacy, police strength, per-capita expenditure, forest cover, IPC
crime counts), plus a set of dummy benchmark "safe city" rows used later
for comparative safety scoring.

District names/coordinates are real Kerala districts (approximate centers);
all population/crime/police/expenditure figures are randomly generated for
demonstration and are NOT official statistics. Swap this command for a real
ingestion job (reading data.gov.in exports, a crime-records API, etc.) to
go from demo to production without touching any other stage of the
pipeline.
"""
import random

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import District
from clustering.models import BenchmarkCity

# name, lat, lon, base_population, base_forest_cover_pct
KERALA_DISTRICTS = [
    ("Thiruvananthapuram", 8.5241, 76.9366, 3_300_000, 10),
    ("Kollam", 8.8932, 76.6141, 2_600_000, 18),
    ("Pathanamthitta", 9.2648, 76.7870, 1_200_000, 45),
    ("Alappuzha", 9.4981, 76.3388, 2_100_000, 4),
    ("Kottayam", 9.5916, 76.5222, 1_970_000, 22),
    ("Idukki", 9.9189, 77.1025, 1_100_000, 52),
    ("Ernakulam", 9.9312, 76.2673, 3_280_000, 12),
    ("Thrissur", 10.5276, 76.2144, 3_120_000, 20),
    ("Palakkad", 10.7867, 76.6548, 2_800_000, 30),
    ("Malappuram", 11.0510, 76.0711, 4_100_000, 25),
    ("Kozhikode", 11.2588, 75.7804, 3_080_000, 18),
    ("Wayanad", 11.6854, 76.1320, 820_000, 48),
    ("Kannur", 11.8745, 75.3704, 2_520_000, 30),
    ("Kasaragod", 12.4996, 74.9869, 1_300_000, 28),
]

BENCHMARK_CITIES = [
    # name, country, crime/100k, police/100k, literacy, reference safety score
    ("Reykjavik", "Iceland", 22, 330, 99.0, 96),
    ("Zurich", "Switzerland", 28, 300, 99.0, 94),
    ("Singapore", "Singapore", 18, 380, 97.0, 97),
    ("Tokyo", "Japan", 20, 250, 99.0, 95),
    ("Helsinki", "Finland", 30, 310, 99.5, 93),
]


class Command(BaseCommand):
    help = "Stage 1: generate synthetic district + benchmark-city data for the SafeRoutes demo."

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=7, help="Random seed for reproducibility")

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(options["seed"])

        District.objects.all().delete()
        BenchmarkCity.objects.all().delete()

        for name, lat, lon, base_pop, forest_cover in KERALA_DISTRICTS:
            population = int(base_pop * random.uniform(0.92, 1.08))

            # deliberately vary police coverage and literacy so clusters separate
            police_per_100k_target = random.uniform(70, 230)
            police_strength = int(police_per_100k_target * population / 100_000)

            literacy_rate = round(random.uniform(89.5, 97.5), 1)
            per_capita_expenditure = round(random.uniform(9000, 26000), 0)

            # crime counts: loosely tied to population + an independent risk factor
            risk_factor = random.uniform(0.5, 2.2)
            crime_rape = max(0, int(random.gauss(population / 100_000 * 1.4 * risk_factor, 3)))
            crime_kidnapping = max(0, int(random.gauss(population / 100_000 * 1.1 * risk_factor, 2)))
            crime_other = max(0, int(random.gauss(population / 100_000 * 3.5 * risk_factor, 6)))

            District.objects.create(
                name=name,
                state="Kerala",
                latitude=lat,
                longitude=lon,
                population=population,
                literacy_rate=literacy_rate,
                police_strength=police_strength,
                per_capita_expenditure=per_capita_expenditure,
                forest_cover_pct=round(forest_cover * random.uniform(0.85, 1.15), 1),
                crime_rape=crime_rape,
                crime_kidnapping=crime_kidnapping,
                crime_other_ipc_women=crime_other,
                population_growth_rate=round(random.uniform(-0.5, 1.8), 2),
            )

        for name, country, crime, police, literacy, ref_score in BENCHMARK_CITIES:
            BenchmarkCity.objects.create(
                name=name,
                country=country,
                crime_rate_per_100k=crime,
                police_per_100k=police,
                literacy_rate=literacy,
                reference_safety_score=ref_score,
            )

        self.stdout.write(self.style.SUCCESS(
            f"Ingested {District.objects.count()} districts and "
            f"{BenchmarkCity.objects.count()} benchmark cities."
        ))
        self.stdout.write("Next: python manage.py train_clusters")
