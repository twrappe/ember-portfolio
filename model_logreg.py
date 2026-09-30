"""
Logistic regression model: elevated stress vs. baseline.

Features (daily vector)
-----------------------
hrv_balance     – Oura HRV-balance contributor score (0-100); proxy for HRV
                  mean / RMSSD until raw RMSSD endpoint data is available
rhr             – resting heart rate (bpm)
temp_deviation  – skin-temperature deviation (°C)
sleep_score     – Oura daily sleep score (0-100)
deep_sleep_pct  – deep-sleep contributor score (0-100)
rem_pct         – REM-sleep contributor score (0-100)

Target (label source priority)
------------------------------
1. Mood-journal (mood_log.csv evening classification_day) — used when present;
   overrides the Oura flag for that day.
2. Oura composite_deviation flag — fallback for all unlabelled days.
   MODERATE / HIGH → 1,  NORMAL → 0.

This means the model trains on all Oura data immediately and automatically
promotes mood-journal entries to ground-truth as they accumulate.

Model
-----
LogisticRegression(C=0.1, max_iter=1000, class_weight="balanced")
  - L2 regularisation keeps weights small on a tiny dataset
  - INT8-quantisation-friendly output (no heavy float arithmetic)
  - Interpretable coefficients provide a performance floor to beat

Usage
-----
  python model_logreg.py            # train, evaluate, save
  python model_logreg.py --predict  # load saved model and score today
"""

import ast
import argparse
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneOut
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)

DATA_DIR = Path("data")
MODEL_PATH = Path("models") / "logreg_stress.joblib"
MODEL_MANIFEST_PATH = DATA_DIR / "model_version_manifest.json"
PREDICTION_PATH = DATA_DIR / "model_prediction_latest.json"

FEATURES = [
    "hrv_balance",
    "rhr",
    "temp_deviation",
    "sleep_score",
    "deep_sleep_pct",
    "rem_pct",
]

# Oura deviation flags that map to label=1 (elevated)
ELEVATED_FLAGS = {"MODERATE", "HIGH"}

# Mood-journal classifications that map to label=1 (elevated)
ELEVATED_MOOD_LABELS = {"Mildly elevated", "Elevated", "Hypomanic", "Manic", "Mildly depressed", "Depressed"}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

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
    df = pd.read_csv(DATA_DIR / "daily_readiness.csv")
    df["day"] = pd.to_datetime(df["day"]).dt.date
    contrib = df["contributors"].apply(_safe_parse_contributors)
    cdf = pd.DataFrame(contrib.tolist())
    cdf = cdf.reindex(columns=["hrv_balance", "resting_heart_rate"])
    return pd.concat(
        [df[["day", "temperature_deviation"]], cdf[["hrv_balance", "resting_heart_rate"]]],
        axis=1,
    ).rename(columns={"temperature_deviation": "temp_deviation", "resting_heart_rate": "rhr"})


def load_sleep() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "daily_sleep.csv")
    df["day"] = pd.to_datetime(df["day"]).dt.date
    contrib = df["contributors"].apply(_safe_parse_contributors)
    cdf = pd.DataFrame(contrib.tolist())
    cdf = cdf.reindex(columns=["deep_sleep", "rem_sleep"])
    return pd.concat(
        [df[["day", "score"]], cdf[["deep_sleep", "rem_sleep"]]],
        axis=1,
    ).rename(columns={"score": "sleep_score", "deep_sleep": "deep_sleep_pct", "rem_sleep": "rem_pct"})


def load_oura_labels() -> pd.DataFrame:
    """Oura composite_deviation flag as the fallback binary target.

    Rows with flag=='unknown' (insufficient prior data for a valid baseline)
    are dropped so they are not silently mislabelled as 0.
    """
    df = pd.read_csv(DATA_DIR / "deviation_scores.csv")
    df["day"] = pd.to_datetime(df["day"]).dt.date
    df = df[df["flag"] != "unknown"].copy()
    df["label_oura"] = df["flag"].apply(lambda f: 1 if f in ELEVATED_FLAGS else 0)
    return df[["day", "flag", "composite_deviation", "label_oura"]]


def load_mood_labels() -> pd.DataFrame:
    """Evening mood-journal classifications as ground-truth overrides.

    Returns only rows that have a classification_day value.
    label=1  elevated (see ELEVATED_MOOD_LABELS)
    label=0  baseline (Euthymic / stable)
    """
    path = DATA_DIR / "mood_log.csv"
    if not path.exists():
        return pd.DataFrame(columns=["day", "classification_day", "label_mood"])
    df = pd.read_csv(path)
    evening = df[df["session"] == "evening"].copy()
    evening["day"] = pd.to_datetime(evening["date"]).dt.date
    evening = evening[["day", "classification_day"]].dropna(subset=["classification_day"])
    evening["label_mood"] = evening["classification_day"].apply(
        lambda c: 1 if c in ELEVATED_MOOD_LABELS else 0
    )
    return evening[["day", "classification_day", "label_mood"]]


def build_dataset() -> pd.DataFrame:
    readiness = load_readiness()
    sleep = load_sleep()
    oura = load_oura_labels()
    mood = load_mood_labels()

    df = readiness.merge(sleep, on="day").merge(oura, on="day", how="inner")
    df = df.merge(mood, on="day", how="left")

    # Mood-journal overrides Oura flag where present; Oura flag is the fallback.
    df["label"] = df["label_mood"].combine_first(df["label_oura"]).astype(int)
    df["label_source"] = df["label_mood"].apply(
        lambda v: "mood" if pd.notna(v) else "oura"
    )

    df = df.dropna(subset=FEATURES)
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Training & evaluation
# ---------------------------------------------------------------------------

def make_pipeline() -> Pipeline:
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(C=0.1, max_iter=1000, class_weight="balanced", random_state=42)),
    ])


def evaluate_loocv(X: np.ndarray, y: np.ndarray) -> dict:
    """Leave-one-out CV — appropriate when n is small."""
    loo = LeaveOneOut()
    y_true, y_pred, y_prob = [], [], []

    for train_idx, test_idx in loo.split(X):
        pipe = make_pipeline()
        pipe.fit(X[train_idx], y[train_idx])
        pred = pipe.predict(X[test_idx])
        prob = pipe.predict_proba(X[test_idx])[:, 1]
        y_true.append(y[test_idx][0])
        y_pred.append(pred[0])
        y_prob.append(prob[0])

    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "confusion_matrix": confusion_matrix(y_true, y_pred),
        "report": classification_report(
            y_true, y_pred, target_names=["baseline", "elevated"], zero_division=0
        ),
        "report_dict": classification_report(
            y_true, y_pred, target_names=["baseline", "elevated"], zero_division=0, output_dict=True
        ),
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            metrics["roc_auc"] = roc_auc_score(y_true, y_prob)
        except ValueError:
            metrics["roc_auc"] = float("nan")  # only one class present
    return metrics


def print_coefficients(pipe: Pipeline) -> None:
    scaler: StandardScaler = pipe.named_steps["scaler"]
    clf: LogisticRegression = pipe.named_steps["clf"]
    # Standardised coefficients (effect per 1 SD)
    coefs = clf.coef_[0]
    print("\nCoefficients (standardised — effect per 1 SD):")
    print(f"  {'feature':<20s}  {'coef':>8s}")
    print(f"  {'-'*20}  {'-'*8}")
    for feat, coef in sorted(zip(FEATURES, coefs), key=lambda x: abs(x[1]), reverse=True):
        print(f"  {feat:<20s}  {coef:>8.4f}")
    print(f"\n  Intercept: {clf.intercept_[0]:.4f}")


def summarize_metrics(metrics: dict) -> dict:
    report_dict = metrics.get("report_dict", {})
    elevated = report_dict.get("elevated", {})
    baseline = report_dict.get("baseline", {})
    return {
        "accuracy": float(metrics.get("accuracy", 0.0)),
        "roc_auc": float(metrics.get("roc_auc", float("nan"))),
        "elevated_recall": float(elevated.get("recall", 0.0)),
        "elevated_precision": float(elevated.get("precision", 0.0)),
        "baseline_recall": float(baseline.get("recall", 0.0)),
    }


def evaluate_label_source_metrics(df: pd.DataFrame) -> dict:
    """Summarize model performance overall and by label source.

    R6 mitigation: report mood-journal and Oura-fallback performance separately so
    blended metrics do not hide circularity or inflate the apparent model quality.
    """
    overall = summarize_metrics(evaluate_loocv(np.array(df[FEATURES].values, dtype=float), np.array(df["label"].values, dtype=int)))

    by_source: dict[str, dict] = {}
    for source in ("mood", "oura"):
        subset = df[df["label_source"] == source]
        if len(subset) < 3 or subset["label"].nunique() < 2:
            by_source[source] = {
                "n": int(len(subset)),
                "status": "warning",
                "reason": "insufficient_rows_for_stable_loocv",
            }
            continue

        source_metrics = summarize_metrics(
            evaluate_loocv(
                np.array(subset[FEATURES].values, dtype=float),
                np.array(subset["label"].values, dtype=int),
            )
        )
        source_metrics.update({"n": int(len(subset)), "status": "ok"})
        by_source[source] = source_metrics

    return {
        "overall": overall,
        "by_source": by_source,
    }


def should_promote_model(
    candidate: dict,
    incumbent: dict | None,
    *,
    max_elevated_recall_drop: float = 0.05,
    max_accuracy_drop: float = 0.03,
) -> tuple[bool, str]:
    """Decide whether a candidate model can replace active model.

    R2 mitigation: block promotion when candidate significantly regresses holdout proxies,
    reducing risk that poisoned writes silently replace a safer incumbent.
    """
    if incumbent is None:
        return True, "no_incumbent"

    candidate_recall = float(candidate.get("elevated_recall", 0.0))
    incumbent_recall = float(incumbent.get("elevated_recall", 0.0))
    if candidate_recall < (incumbent_recall - max_elevated_recall_drop):
        return False, "elevated_recall_regression"

    candidate_acc = float(candidate.get("accuracy", 0.0))
    incumbent_acc = float(incumbent.get("accuracy", 0.0))
    if candidate_acc < (incumbent_acc - max_accuracy_drop):
        return False, "accuracy_regression"

    return True, "passed"


def load_model_manifest() -> dict | None:
    if not MODEL_MANIFEST_PATH.exists():
        return None
    try:
        return json.loads(MODEL_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_model_manifest(manifest: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def save_versioned_model(pipe: Pipeline, stamp: str) -> Path:
    versioned = MODEL_PATH.parent / f"logreg_stress_{stamp}.joblib"
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, versioned)
    return versioned


# ---------------------------------------------------------------------------
# Prediction helper
# ---------------------------------------------------------------------------

def predict_today(pipe: Pipeline) -> dict | None:
    readiness = load_readiness()
    sleep = load_sleep()
    df = readiness.merge(sleep, on="day")
    today_row = df[df["day"] == df["day"].max()].copy()
    if today_row.empty:
        print("No data available for today.")
        return None

    missing = [f for f in FEATURES if today_row[f].isna().any()]
    if missing:
        print(f"Missing features for today: {missing}")
        return None

    X = today_row[FEATURES].values
    prob = pipe.predict_proba(X)[0, 1]
    pred = pipe.predict(X)[0]

    scaler: StandardScaler = pipe.named_steps["scaler"]
    clf: LogisticRegression = pipe.named_steps["clf"]
    raw = today_row[FEATURES].iloc[0].astype(float).values
    z = (raw - scaler.mean_) / scaler.scale_
    coefs = clf.coef_[0]
    contributions = z * coefs
    explanation = []
    for feat, raw_val, z_val, coef_val, contrib_val in zip(FEATURES, raw, z, coefs, contributions):
        explanation.append({
            "feature": feat,
            "raw": round(float(raw_val), 4),
            "z": round(float(z_val), 4),
            "coef": round(float(coef_val), 4),
            "contribution": round(float(contrib_val), 4),
            "direction": "toward_elevated" if float(contrib_val) > 0 else "toward_baseline",
        })
    explanation.sort(key=lambda row: abs(float(row["contribution"])), reverse=True)
    label = "ELEVATED" if pred == 1 else "BASELINE"
    day_str = str(today_row["day"].values[0])
    result = {
        "day": day_str,
        "prediction": label,
        "p_elevated": round(float(prob), 4),
        "model": "logreg_stress",
        "explanation": explanation,
    }
    print(f"\nPrediction for {day_str}: {label}  (p_elevated={prob:.3f})")
    return result


def save_latest_prediction(result: dict | None) -> None:
    if not result:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PREDICTION_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f)
    print(f"Saved prediction -> {PREDICTION_PATH}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predict", action="store_true", help="Score today using saved model")
    args = parser.parse_args()

    if args.predict:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"No saved model at {MODEL_PATH}. Run without --predict first.")
        pipe = joblib.load(MODEL_PATH)
        result = predict_today(pipe)
        save_latest_prediction(result)
        return

    # --- Build dataset ---
    df = build_dataset()
    n = len(df)
    n_elevated = int(df["label"].sum())
    n_mood = int((df["label_source"] == "mood").sum())
    n_oura = int((df["label_source"] == "oura").sum())
    print(f"Dataset: {n} days  ({n_elevated} elevated, {n - n_elevated} baseline)")
    print(f"Label sources: {n_mood} mood-journal override(s), {n_oura} Oura fallback(s)")

    if n < 2:
        raise RuntimeError("Need at least 2 labelled days to train.")

    X: np.ndarray = np.array(df[FEATURES].values, dtype=float)
    y: np.ndarray = np.array(df["label"].values, dtype=int)

    # --- LOOCV evaluation ---
    print(f"\nLeave-one-out CV  (n={n})")
    print("NOTE: with n={}, these metrics have very high variance.".format(n))
    print("      Collect more labelled days for reliable estimates.\n")

    metrics = evaluate_loocv(X, y)
    print(f"  Accuracy : {metrics['accuracy']:.2f}")
    print(f"  ROC-AUC  : {metrics['roc_auc']:.2f}")
    print("\nConfusion matrix (rows=true, cols=pred):")
    print(metrics["confusion_matrix"])
    print("\nClassification report:")
    print(metrics["report"])

    metric_summary = summarize_metrics(metrics)
    source_metric_summary = evaluate_label_source_metrics(df)
    print("\nLabel-source split metrics:")
    print(f"  Overall: {source_metric_summary['overall']}")
    for source, summary in source_metric_summary["by_source"].items():
        print(f"  {source}: {summary}")

    # --- Train final model on all data ---
    pipe = make_pipeline()
    pipe.fit(X, y)
    print_coefficients(pipe)

    # --- Versioning + promotion gate ---
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate_path = save_versioned_model(pipe, stamp)

    manifest = load_model_manifest() or {
        "active_model": None,
        "active_metrics": None,
        "history": [],
    }
    incumbent_metrics = manifest.get("active_metrics")
    promote, reason = should_promote_model(metric_summary, incumbent_metrics)

    entry = {
        "version": stamp,
        "artifact": str(candidate_path),
        "metrics": metric_summary,
        "source_metrics": source_metric_summary,
        "label_source_counts": {
            "mood": n_mood,
            "oura": n_oura,
        },
        "dataset_size": n,
        "promotion_decision": "promoted" if promote else "rejected",
        "decision_reason": reason,
    }
    manifest.setdefault("history", []).append(entry)

    if promote:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipe, MODEL_PATH)
        manifest["active_model"] = str(MODEL_PATH)
        manifest["active_metrics"] = metric_summary
        print(f"\nModel promoted -> {MODEL_PATH}")
    else:
        print(f"\nModel promotion blocked ({reason}); active model retained.")

    save_model_manifest(manifest)
    print(f"Model manifest updated -> {MODEL_MANIFEST_PATH}")

    # --- Score today if data is available ---
    result = predict_today(pipe)
    save_latest_prediction(result)


if __name__ == "__main__":
    main()
