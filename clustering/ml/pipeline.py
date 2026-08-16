"""
Stage 2-4 of the SafeRoutes pipeline: pre-processing, feature selection,
clustering (K-Means + Gaussian Mixture Model) and benchmark-based safety
scoring. Runnable standalone from the `train_clusters` management command.
"""
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score

from core.models import District
from clustering.models import BenchmarkCity, SafetyCluster, DistrictClusterAssignment

FEATURE_COLUMNS = [
    "crime_rate_per_100k",
    "police_per_100k",
    "literacy_rate",
    "per_capita_expenditure",
    "forest_cover_pct",
]

TIER_ORDER = ["I", "II", "III", "IV"]
TIER_COLORS = {
    "I": "#35C4A1",    # Safe Teal
    "II": "#7CC6A6",   # softer teal-green
    "III": "#F2A65A",  # Beacon Amber
    "IV": "#E8546B",   # Risk Coral
}


def _normalize(series):
    lo, hi = series.min(), series.max()
    if hi - lo < 1e-9:
        return series * 0 + 0.5
    return (series - lo) / (hi - lo)


def load_district_frame():
    """Stage 1->2: pull districts from the DB and (re)compute engineered fields."""
    qs = District.objects.all()
    if not qs.exists():
        raise ValueError("No districts found. Run `manage.py generate_synthetic_data` first.")

    df = pd.DataFrame.from_records(qs.values(
        "id", "name", "latitude", "longitude", "population", "literacy_rate",
        "police_strength", "per_capita_expenditure", "forest_cover_pct",
        "crime_rape", "crime_kidnapping", "crime_other_ipc_women",
    ))
    df["total_crimes"] = df["crime_rape"] + df["crime_kidnapping"] + df["crime_other_ipc_women"]
    df["crime_rate_per_100k"] = df["total_crimes"] / df["population"] * 100_000
    df["police_per_100k"] = df["police_strength"] / df["population"] * 100_000

    state_avg_literacy = df["literacy_rate"].mean()
    df["literacy_disparity"] = (df["literacy_rate"] - state_avg_literacy).abs()

    # persist engineered fields back onto the District rows (Stage 2 output)
    for row in df.itertuples():
        District.objects.filter(pk=row.id).update(
            crime_rate_per_100k=round(row.crime_rate_per_100k, 3),
            police_per_100k=round(row.police_per_100k, 3),
            literacy_disparity=round(row.literacy_disparity, 3),
        )
    return df


def feature_correlation_report(df):
    """Stage 4.3: Pearson + Spearman correlation matrices for feature selection."""
    pearson = df[FEATURE_COLUMNS].corr(method="pearson").round(3)
    spearman = df[FEATURE_COLUMNS].corr(method="spearman").round(3)
    return pearson, spearman


def _select_k(X_scaled, candidates=(3, 4)):
    """Pick cluster count using silhouette score, as described in the proposal."""
    best_k, best_score, best_labels, best_model = None, -1, None, None
    for k in candidates:
        model = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = model.fit_predict(X_scaled)
        score = silhouette_score(X_scaled, labels)
        if score > best_score:
            best_k, best_score, best_labels, best_model = k, score, labels, model
    return best_k, best_score, best_labels, best_model


def _select_gmm(X_scaled, candidates=(3, 4)):
    best_k, best_bic, best_labels, best_model = None, np.inf, None, None
    for k in candidates:
        model = GaussianMixture(n_components=k, random_state=42, n_init=5)
        labels = model.fit_predict(X_scaled)
        bic = model.bic(X_scaled)
        if bic < best_bic:
            best_k, best_bic, best_labels, best_model = k, bic, labels, model
    return best_k, best_bic, best_labels, best_model


def compute_safety_scores(df):
    """
    Stage 4: benchmark each district against globally recognized safe
    cities on the three shared indicators (crime rate, police presence,
    literacy), producing a 0-100 comparative safety score.
    """
    benchmarks = pd.DataFrame.from_records(
        BenchmarkCity.objects.values("crime_rate_per_100k", "police_per_100k", "literacy_rate")
    )
    combined = pd.concat([
        df[["crime_rate_per_100k", "police_per_100k", "literacy_rate"]],
        benchmarks,
    ], ignore_index=True) if not benchmarks.empty else df[["crime_rate_per_100k", "police_per_100k", "literacy_rate"]]

    crime_n = 1 - _normalize(combined["crime_rate_per_100k"])
    police_n = _normalize(combined["police_per_100k"])
    literacy_n = _normalize(combined["literacy_rate"])
    combined_score = (0.5 * crime_n + 0.3 * police_n + 0.2 * literacy_n) * 100

    df = df.copy()
    df["safety_score"] = combined_score.iloc[: len(df)].round(2).values
    return df


def _tier_for_rank(rank, n_clusters):
    # rank 0 = safest cluster
    if n_clusters == 3:
        mapping = {0: "I", 1: "II", 2: "IV"}
    else:
        mapping = {0: "I", 1: "II", 2: "III", 3: "IV"}
    return mapping.get(rank, "IV")


def run_pipeline(stdout=None):
    def log(msg):
        if stdout:
            stdout.write(msg)
        else:
            print(msg)

    df = load_district_frame()
    log(f"Loaded {len(df)} districts.")

    pearson, spearman = feature_correlation_report(df)
    log("Pearson correlation (feature selection):\n" + pearson.to_string())

    df = compute_safety_scores(df)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df[FEATURE_COLUMNS])

    results = {}
    for algo_name, selector in (("kmeans", _select_k), ("gmm", _select_gmm)):
        k, metric, labels, model = selector(X_scaled)
        sil = silhouette_score(X_scaled, labels)
        ch = calinski_harabasz_score(X_scaled, labels)
        db = davies_bouldin_score(X_scaled, labels)
        log(f"[{algo_name}] chosen k={k} silhouette={sil:.3f} calinski_harabasz={ch:.1f} davies_bouldin={db:.3f}")
        results[algo_name] = {"k": k, "labels": labels, "silhouette": sil}

        # rank raw cluster indices by mean safety score, safest first
        tmp = df.copy()
        tmp["_label"] = labels
        cluster_means = tmp.groupby("_label")["safety_score"].mean().sort_values(ascending=False)
        rank_of_label = {label: rank for rank, label in enumerate(cluster_means.index)}

        SafetyCluster.objects.filter(algorithm=algo_name).delete()
        cluster_objs = {}
        for label, mean_score in cluster_means.items():
            rank = rank_of_label[label]
            tier = _tier_for_rank(rank, k)
            count = int((labels == label).sum())
            cluster_objs[label] = SafetyCluster.objects.create(
                algorithm=algo_name,
                cluster_index=int(label),
                tier=tier,
                color_hex=TIER_COLORS[tier],
                avg_safety_score=round(float(mean_score), 2),
                district_count=count,
                silhouette_score=round(float(sil), 4),
            )

        if algo_name == "kmeans":
            # K-Means is used as the primary, user-facing safety assignment.
            # GMM clusters above are still saved (for admin comparison) but
            # don't overwrite the one-per-district assignment table.
            DistrictClusterAssignment.objects.all().delete()
            for row, label in zip(df.itertuples(), labels):
                DistrictClusterAssignment.objects.update_or_create(
                    district_id=row.id,
                    defaults={
                        "cluster": cluster_objs[label],
                        "safety_score": round(float(row.safety_score), 2),
                    },
                )

    log("Pipeline complete. K-Means assignments are used as the primary safety map;"
        " GMM clusters are stored for comparison in the admin panel.")
    return results
