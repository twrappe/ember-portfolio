import ast
import pandas as pd
import numpy as np
from datetime import date, timedelta

DATA_DIR = "data"
LOOKBACK_DAYS = 30
SCORE_METRICS = [
    "temperature_deviation",
    "hrv_balance",
    "resting_heart_rate",
    "recovery_index",
    "previous_night",
    "sleep_balance",
]


def _safe_parse_contributors(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if pd.isna(raw):
        return {}
    try:
        parsed = ast.literal_eval(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}

def load_readiness() -> pd.DataFrame:
    df = pd.read_csv(f"{DATA_DIR}/daily_readiness.csv")
    df["day"] = pd.to_datetime(df["day"]).dt.date

    # Parse contributors JSON string into columns
    contributors = df["contributors"].apply(_safe_parse_contributors)
    contrib_df = pd.DataFrame(contributors.tolist())

    df = pd.concat([df[["day", "score", "temperature_deviation"]], contrib_df], axis=1)

    for metric in SCORE_METRICS:
        if metric not in df.columns:
            df[metric] = np.nan

    df = df.sort_values("day").reset_index(drop=True)
    return df

def compute_baseline(df: pd.DataFrame, as_of: date) -> dict:
    """Returns mean and std for each metric over the 30-day window ending on as_of."""
    window_start = as_of - timedelta(days=LOOKBACK_DAYS)
    baseline_df = df[(df["day"] > window_start) & (df["day"] <= as_of)].copy()

    stats = {}
    for metric in SCORE_METRICS:
        col = baseline_df[metric].dropna().astype(float)
        stats[metric] = {"mean": col.mean(), "std": col.std()}
    return stats

def z_score(value, mean, std) -> float | None:
    if pd.isna(value) or std == 0 or pd.isna(std):
        return None
    return round((float(value) - mean) / std, 2)

def score_day(row: pd.Series, baseline: dict) -> dict:
    scores = {"day": row["day"], "readiness_score": row["score"]}
    z_scores = {}
    for metric in SCORE_METRICS:
        val = row.get(metric)
        b = baseline.get(metric, {})
        z = z_score(val, b.get("mean"), b.get("std"))
        z_scores[f"z_{metric}"] = z

    # Composite deviation: mean of absolute z-scores across available metrics
    available = [v for v in z_scores.values() if v is not None]
    scores["composite_deviation"] = round(np.mean(np.abs(available)), 2) if available else None
    scores.update(z_scores)
    return scores

def flag(composite: float | None) -> str:
    if composite is None:
        return "unknown"
    if composite >= 2.0:
        return "HIGH"
    if composite >= 1.0:
        return "MODERATE"
    return "NORMAL"

def main():
    df = load_readiness()
    today = date.today()

    # Display-only summary: current 30-day baseline as of today
    display_baseline = compute_baseline(df, today)
    print("\n=== Baseline (30-day means, as of today) ===")
    for metric, stats in display_baseline.items():
        print(f"  {metric:30s} mean={stats['mean']:.2f}  std={stats['std']:.2f}")

    # Score ALL available days using a strictly causal rolling baseline:
    # day D is scored against data from (D-31, D-1] only — D itself is excluded.
    # This eliminates look-ahead leakage and produces valid training labels.
    results = []
    for _, row in df.iterrows():
        day_baseline = compute_baseline(df, row["day"] - timedelta(days=1))
        scored = score_day(row, day_baseline)
        scored["flag"] = flag(scored["composite_deviation"])
        results.append(scored)

    results_df = pd.DataFrame(results)
    results_df.to_csv(f"{DATA_DIR}/deviation_scores.csv", index=False)

    print("\n=== Deviation Scores (last 7 days) ===")
    display_cols = ["day", "readiness_score", "composite_deviation", "flag"] + \
                   [f"z_{m}" for m in SCORE_METRICS]
    print(results_df[display_cols].tail(7).to_string(index=False))

    print("\n=== Flag Summary ===")
    print(results_df["flag"].value_counts().to_string())

if __name__ == "__main__":
    main()