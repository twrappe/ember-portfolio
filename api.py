"""
EMBER API Server
Run with: uvicorn api:app --reload --port 8000
"""
 
import ast
import csv
import json
from pathlib import Path
import os
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
 
app = FastAPI(title="EMBER API")
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type"],
)
 
DATA_DIR = Path("data")
MODEL_PREDICTION_PATH = DATA_DIR / "model_prediction_latest.json"
API_TOKEN = os.getenv("EMBER_API_TOKEN", "ember-local-dev-token")

PREDICTION_REQUIRED_FIELDS = {
    "day": str,
    "prediction": str,
    "p_elevated": (int, float),
    "model": str,
}

EXPLANATION_REQUIRED_FIELDS = {
    "feature": str,
    "raw": (int, float),
    "z": (int, float),
    "coef": (int, float),
    "contribution": (int, float),
    "direction": str,
}


def require_auth(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    if not token or token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bearer token")


def is_model_prediction_compatible(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False

    for key, expected_type in PREDICTION_REQUIRED_FIELDS.items():
        if key not in payload or not isinstance(payload[key], expected_type):
            return False

    explanation = payload.get("explanation")
    if explanation is None:
        return True
    if not isinstance(explanation, list):
        return False

    for item in explanation:
        if not isinstance(item, dict):
            return False
        for key, expected_type in EXPLANATION_REQUIRED_FIELDS.items():
            if key not in item or not isinstance(item[key], expected_type):
                return False
        if item["direction"] not in {"toward_elevated", "toward_baseline"}:
            return False

    return True
 
 
def parse_contributors(raw: str) -> dict:
    """Parse the stringified dict from CSVs safely."""
    try:
        return ast.literal_eval(raw)
    except Exception:
        return {}
 
 
def read_csv(filename: str) -> list[dict]:
    path = DATA_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{filename} not found")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def get_model_prediction() -> dict | None:
    if not MODEL_PREDICTION_PATH.exists():
        return None
    try:
        payload = json.loads(MODEL_PREDICTION_PATH.read_text(encoding="utf-8"))
        return payload if is_model_prediction_compatible(payload) else None
    except Exception:
        return None
 
 
# ─────────────────────────────────────────────
# GET /api/readiness
# Returns last 30 days of readiness scores
# ─────────────────────────────────────────────
@app.get("/api/readiness")
def get_readiness(_: None = Depends(require_auth)):
    rows = read_csv("daily_readiness.csv")
    result = []
    for r in rows[-30:]:
        contributors = parse_contributors(r.get("contributors", "{}"))
        result.append({
            "date": r["day"],
            "score": int(r["score"]) if r["score"] else None,
            "temperature_deviation": float(r["temperature_deviation"]) if r["temperature_deviation"] else None,
            "hrv_balance": contributors.get("hrv_balance"),
            "resting_heart_rate": contributors.get("resting_heart_rate"),
            "sleep_balance": contributors.get("sleep_balance"),
            "recovery_index": contributors.get("recovery_index"),
        })
    return result
 
 
# ─────────────────────────────────────────────
# GET /api/sleep
# Returns last 30 days of sleep scores
# ─────────────────────────────────────────────
@app.get("/api/sleep")
def get_sleep(_: None = Depends(require_auth)):
    rows = read_csv("daily_sleep.csv")
    result = []
    for r in rows[-30:]:
        contributors = parse_contributors(r.get("contributors", "{}"))
        result.append({
            "date": r["day"],
            "score": int(r["score"]) if r["score"] else None,
            "total_sleep": contributors.get("total_sleep"),
            "efficiency": contributors.get("efficiency"),
            "deep_sleep": contributors.get("deep_sleep"),
            "rem_sleep": contributors.get("rem_sleep"),
            "restfulness": contributors.get("restfulness"),
        })
    return result
 
 
# ─────────────────────────────────────────────
# GET /api/deviation
# Returns last 30 days of deviation scores + flags
# ─────────────────────────────────────────────
@app.get("/api/deviation")
def get_deviation(_: None = Depends(require_auth)):
    rows = read_csv("deviation_scores.csv")
    result = []
    for r in rows[-30:]:
        result.append({
            "date": r["day"],
            "readiness_score": int(r["readiness_score"]) if r["readiness_score"] else None,
            "composite_deviation": float(r["composite_deviation"]) if r["composite_deviation"] else None,
            "z_temperature": float(r["z_temperature_deviation"]) if r.get("z_temperature_deviation") else None,
            "z_hrv": float(r["z_hrv_balance"]) if r.get("z_hrv_balance") else None,
            "z_rhr": float(r["z_resting_heart_rate"]) if r.get("z_resting_heart_rate") else None,
            "z_sleep_balance": float(r["z_sleep_balance"]) if r.get("z_sleep_balance") else None,
            "flag": r.get("flag", "NORMAL"),
        })
    return result
 
 
# ─────────────────────────────────────────────
# GET /api/summary
# Returns the latest clinical summary
# ─────────────────────────────────────────────
@app.get("/api/summary")
def get_summary(_: None = Depends(require_auth)):
    path = DATA_DIR / "summaries.jsonl"
    if not path.exists():
        raise HTTPException(status_code=404, detail="summaries.jsonl not found")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        raise HTTPException(status_code=404, detail="No summaries found")
    # Return the last entry
    return json.loads(lines[-1])
 
 
# ─────────────────────────────────────────────
# GET /api/dashboard
# Single call returning everything the frontend needs
# ─────────────────────────────────────────────
@app.get("/api/dashboard")
def get_dashboard(_: None = Depends(require_auth)):
    readiness = get_readiness()
    sleep = get_sleep()
    deviation = get_deviation()
    summary = get_summary()
    model_prediction = get_model_prediction()
 
    # Merge by date into unified metrics
    readiness_map = {r["date"]: r for r in readiness}
    sleep_map = {s["date"]: s for s in sleep}
    deviation_map = {d["date"]: d for d in deviation}
 
    all_dates = sorted(set(list(readiness_map) + list(sleep_map) + list(deviation_map)))
 
    metrics = []
    for date in all_dates[-7:]:  # last 7 days for chart
        r = readiness_map.get(date, {})
        s = sleep_map.get(date, {})
        d = deviation_map.get(date, {})
        metrics.append({
            "date": date,
            "readiness": r.get("score"),
            "sleep": s.get("score"),
            "hrv": r.get("hrv_balance"),
            "riskScore": round(min((d.get("composite_deviation") or 0) * 40, 100)),
            "flag": d.get("flag", "NORMAL"),
            "composite_deviation": d.get("composite_deviation"),
        })
 
    # Current risk from latest deviation entry
    latest_dev = deviation[-1] if deviation else {}
    current_risk = round(min((latest_dev.get("composite_deviation") or 0) * 40, 100))
 
    # Alerts from MODERATE/HIGH flags in last 7 days
    alerts = []
    for d in deviation[-7:]:
        if d.get("flag") in ("MODERATE", "HIGH"):
            alerts.append({
                "id": d["date"],
                "date": d["date"],
                "severity": "high" if d["flag"] == "HIGH" else "medium",
                "message": f"Composite deviation {d['composite_deviation']:.2f} on {d['date']}",
                "flag": d["flag"],
            })
 
    return {
        "metrics": metrics,
        "alerts": alerts,
        "currentRisk": current_risk,
        "lastSync": readiness[-1]["date"] if readiness else None,
        "summary": summary,
        "modelPrediction": model_prediction,
    }