# SafeRoutes

A data-driven system for women's safety: unsupervised clustering of
district-level crime/police/socio-economic data into safety tiers, benchmarked
against globally recognized safe cities, layered under a GPS route planner
that flags deviations into high-risk zones. Built with Django (server-rendered
templates + a small JSON API for the map layer), scikit-learn, and Leaflet.

This implements the 5-stage pipeline from the project proposal:

1. **Data Ingestion** — `core` app, `generate_synthetic_data` command
2. **Data Pre-processing** — feature engineering in `clustering/ml/pipeline.py`
3. **Clustering Model** — K-Means + Gaussian Mixture Model, `train_clusters` command
4. **Safety Scoring & Heatmap** — benchmark-based scoring, Leaflet heatmap page
5. **Maps & Cab Integration** — route planning, simulated GPS pings, deviation alerts

## Project layout

```
saferoutes_project/   Django settings, root URLconf
core/                  District model, admin, synthetic data generator (Stage 1)
clustering/            BenchmarkCity/SafetyCluster models, ML pipeline (Stages 2-4)
tracking/              Route/GPSPing/Alert models, route + simulation logic (Stage 5)
dashboard/             Views, templates, static CSS/JS, JSON endpoints (UI)
```

## Setup

Requires Python 3.11+.

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate
python manage.py generate_synthetic_data   # Stage 1: synthetic districts + benchmark cities
python manage.py train_clusters            # Stages 2-4: preprocess, cluster, score

python manage.py createsuperuser           # optional, for /admin/
python manage.py runserver
```

Then open **http://127.0.0.1:8000/**.

- `/` — cluster overview + district table
- `/heatmap/` — Leaflet safety heatmap
- `/routes/plan/` — pick a source/destination district, generate a route,
  optionally simulate a mid-journey deviation into a high-risk zone
- `/alerts/` — all deviation alerts raised
- `/admin/` — inspect/edit raw + engineered data, clusters, routes, pings

## Notes on the demo data

- District names/coordinates are real Kerala districts; population, crime,
  police-strength, expenditure and forest-cover figures are **synthetically
  generated** (`core/management/commands/generate_synthetic_data.py`) in the
  shape of the real Open Government Data Platform fields named in the
  proposal. Swap that one file for a real ingestion job (data.gov.in export,
  crime-records API, etc.) — nothing downstream needs to change.
- Benchmark "safe city" figures (Reykjavik, Zurich, Singapore, Tokyo,
  Helsinki) are illustrative reference values for demonstration, matching the
  proposal's "dummy benchmark data" step — not sourced from a live feed.
- MySQL was named in the original proposal; the project ships on SQLite for
  zero-config local setup. To switch, change `DATABASES` in
  `saferoutes_project/settings.py` to the `mysql` backend and
  `pip install mysqlclient`.

## Notes on the route/GPS simulation

`plan_route()` interpolates a straight-line path between two district
centers rather than calling a real road-routing engine — this keeps the demo
self-contained with no external API key required. Swap it for a call to the
Google Maps Directions API or OSRM to get real road geometry; everything
downstream (safety buffer, GPS ping simulation, deviation alerts) works the
same way regardless of where the waypoints come from.

`simulate_journey()` walks the planned waypoints and, optionally, nudges one
midpoint toward the nearest high-risk district to simulate a vehicle going
off-route — this is what triggers the real-time deviation alert. In a
production system this would instead consume a live GPS feed from a phone or
vehicle tracker.

## Re-running the ML pipeline

`train_clusters` is idempotent — re-run it any time after changing the
district data (e.g. after editing values in `/admin/`) to regenerate clusters
and scores:

```bash
python manage.py train_clusters
```

It logs the chosen K-Means/GMM cluster count, silhouette / Calinski-Harabasz
/ Davies-Bouldin scores, and the Pearson feature-correlation matrix used for
feature selection.
