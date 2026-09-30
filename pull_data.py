import os
import requests
import pandas as pd
from datetime import date, timedelta
from dotenv import load_dotenv
from token_manager import get_valid_token
from analytics import emit_event

load_dotenv()

BASE_URL = "https://api.ouraring.com/v2/usercollection"
DATA_DIR = "data"
HTTP_TIMEOUT_SECONDS = 20

def get_start_date(name: str) -> str:
    path = os.path.join(DATA_DIR, f"{name}.csv")
    if os.path.exists(path):
        existing = pd.read_csv(path)
        if "day" in existing.columns and not existing.empty:
            existing_days = set(existing["day"])
            start = date.fromisoformat(existing["day"].min())
            today = date.today()
            current = start
            while current <= today:
                if current.isoformat() not in existing_days:
                    return current.isoformat()
                current += timedelta(days=1)
            return (today + timedelta(days=1)).isoformat()  # fully up to date
    return (date.today() - timedelta(days=30)).isoformat()

def fetch(endpoint: str, token: str, start_date: str) -> list:
    end_date = date.today().isoformat()
    session_id = f"sync-{endpoint}-{start_date}"

    emit_event(
        "sync_started",
        session_id,
        {
            "sync_scope": endpoint,
            "start_date": start_date,
            "end_date": end_date,
        },
    )

    if start_date > end_date:
        print(f"  {endpoint} already up to date.")
        emit_event(
            "sync_completed",
            session_id,
            {
                "sync_scope": endpoint,
                "status": "skipped",
                "rows": 0,
            },
        )
        return []

    try:
        resp = requests.get(
            f"{BASE_URL}/{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
            params={"start_date": start_date, "end_date": end_date},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        emit_event(
            "sync_completed",
            session_id,
            {
                "sync_scope": endpoint,
                "status": "success",
                "rows": len(data),
                "http_status": resp.status_code,
            },
        )
        return data
    except Exception as exc:
        emit_event(
            "sync_completed",
            session_id,
            {
                "sync_scope": endpoint,
                "status": "error",
                "error_type": type(exc).__name__,
            },
        )
        raise

def save(df: pd.DataFrame, name: str):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{name}.csv")

    if "day" in df.columns and not df.empty:
        day_values = pd.to_datetime(df["day"], errors="coerce")
        if day_values.isna().any():
            raise ValueError(f"{name}: one or more day values are invalid or non-ISO")

        today = pd.Timestamp(date.today())
        future_mask = day_values > today
        if future_mask.any():
            future_days = sorted(df.loc[future_mask, "day"].astype(str).unique().tolist())
            raise ValueError(f"{name}: future-dated rows are not allowed: {future_days}")

        df = df.copy()
        df["day"] = day_values.dt.date.astype(str)

    if os.path.exists(path):
        existing = pd.read_csv(path)
        # Keep the most recently fetched row for each day so corrected re-pulls win.
        df = pd.concat([existing, df], ignore_index=True).drop_duplicates(subset=["day"], keep="last").sort_values("day")
    elif "day" in df.columns:
        df = df.drop_duplicates(subset=["day"], keep="last").sort_values("day")

    df.to_csv(path, index=False)
    print(f"  Saved {len(df)} rows -> {path}")

def main():
    token = get_valid_token()

    readiness_data = fetch("daily_readiness", token, get_start_date("daily_readiness"))
    df_readiness = pd.DataFrame(readiness_data)
    print("\n=== Daily Readiness ===")
    print(df_readiness.to_string())
    save(df_readiness, "daily_readiness")

    sleep_data = fetch("daily_sleep", token, get_start_date("daily_sleep"))
    df_sleep = pd.DataFrame(sleep_data)
    print("\n=== Daily Sleep ===")
    print(df_sleep.to_string())
    save(df_sleep, "daily_sleep")

if __name__ == "__main__":
    main()