import ast
import json
import os
import requests
import pandas as pd
from datetime import date, timedelta
from dotenv import load_dotenv
from token_manager import get_valid_token

load_dotenv()
HTTP_TIMEOUT_SECONDS = 20
DATA_DIR = "data"
_api_key = os.getenv("ANTHROPIC_API_KEY")
if not _api_key:
    raise EnvironmentError("ANTHROPIC_API_KEY is not set in .env")
ANTHROPIC_API_KEY: str = _api_key

def load_scores() -> pd.DataFrame:
    df = pd.read_csv(f"{DATA_DIR}/deviation_scores.csv")
    df["day"] = pd.to_datetime(df["day"]).dt.date
    return df.sort_values("day")

def load_mood_log() -> pd.DataFrame:
    path = f"{DATA_DIR}/mood_log.csv"
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.sort_values("date")

def build_context(scores_df: pd.DataFrame, mood_df: pd.DataFrame, today: date) -> str:
    window_start = today - timedelta(days=7)
    recent_scores = scores_df[scores_df["day"] > window_start].copy()
    recent_mood = mood_df[mood_df["date"] > window_start].copy() if not mood_df.empty else pd.DataFrame()

    lines = ["=== PHYSIOLOGICAL DATA (last 7 days) ==="]
    for _, row in recent_scores.iterrows():
        lines.append(
            f"{row['day']} | readiness={row['readiness_score']} | "
            f"composite_deviation={row['composite_deviation']} | flag={row['flag']} | "
            f"z_temp={row['z_temperature_deviation']} | z_hrv={row['z_hrv_balance']} | "
            f"z_rhr={row['z_resting_heart_rate']} | z_recovery={row['z_recovery_index']} | "
            f"z_sleep={row['z_previous_night']} | z_sleep_balance={row['z_sleep_balance']}"
        )

    if not recent_mood.empty:
        lines.append("\n=== MOOD JOURNAL (last 7 days) ===")
        for _, row in recent_mood.iterrows():
            session = row.get("session", "")
            if session == "morning":
                lines.append(
                    f"{row['date']} AM | rested={row.get('rested')} | "
                    f"early_waking={row.get('early_waking')} | "
                    f"less_sleep_fine={row.get('less_sleep_fine')} | "
                    f"thought_speed={row.get('thought_speed_morning')} | "
                    f"night_classification={row.get('classification_night')}"
                )
            elif session == "evening":
                lines.append(
                    f"{row['date']} PM | energy={row.get('energy')} | "
                    f"mood={row.get('mood')} | concentration={row.get('concentration')} | "
                    f"irritable={row.get('irritable')} | impulsive={row.get('impulsive')} | "
                    f"withdrew={row.get('withdrew')} | alcohol={row.get('alcohol')} | "
                    f"illness={row.get('illness')} | travel={row.get('travel')} | "
                    f"life_stress={row.get('life_stress')} | "
                    f"classification={row.get('classification_day')} | "
                    f"notes={row.get('notes', '')}"
                )
    else:
        lines.append("\n=== MOOD JOURNAL ===\nNo entries yet.")

    return "\n".join(lines)

def build_prompt(context: str, today: date) -> str:
    return f"""You are a clinical data analyst reviewing physiological and self-reported data for a single subject (adult) engaged in continuous personal health monitoring.

Today's date: {today}
Baseline: 30-day rolling window. Z-scores represent deviation from the subject's personal mean.
Flag thresholds: NORMAL < 1.0, MODERATE 1.0-2.0, HIGH >= 2.0

Scoring metrics:
- temperature_deviation: basal body temperature deviation (°C). Sustained elevation or depression may signal immune activation, hormonal shifts, or autonomic changes.
- hrv_balance: heart rate variability balance score. Low values indicate poor recovery, high allostatic load, or autonomic dysregulation.
- resting_heart_rate: RHR contributor score. Low score = elevated RHR, which may reflect stress, inflammation, poor sleep, or early illness.
- recovery_index: overnight recovery quality. Reflects cardiovascular and autonomic readiness.
- previous_night: prior night sleep quality score.
- sleep_balance: cumulative sleep balance over time. Persistent deficits are a common precursor to mood, cognitive, and immune disruption.

{context}

Write a concise summary (3-5 sentences) for a clinician or the subject reviewing this data. Cover:
1. Overall physiological status relative to personal baseline
2. Any metrics showing sustained or multi-day deviation
3. Cross-reference with mood journal if available
4. Overall signal: NORMAL / WATCH / ALERT and brief rationale

Be specific and data-driven. Do not speculate beyond what the data shows. Flag known confounders (alcohol, illness, travel, life stress) where relevant. Frame observations in terms of general health and recovery rather than assuming any specific diagnosis."""

def call_claude(prompt: str) -> str:
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["content"][0]["text"]

def save_summary(summary: str, today: date):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = f"{DATA_DIR}/summaries.jsonl"
    with open(path, "a") as f:
        f.write(json.dumps({"date": today.isoformat(), "summary": summary}) + "\n")
    print(f"  Saved -> {path}")

def main():
    today = date.today()
    scores_df = load_scores()
    mood_df = load_mood_log()

    context = build_context(scores_df, mood_df, today)
    prompt = build_prompt(context, today)

    print("\n=== Generating clinical summary... ===\n")
    summary = call_claude(prompt)

    print(summary.encode('ascii', errors='replace').decode('ascii'))
    save_summary(summary, today)

if __name__ == "__main__":
    main()