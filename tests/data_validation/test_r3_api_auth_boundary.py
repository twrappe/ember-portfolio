import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api


@pytest.fixture
def seeded_api_data(tmp_path, monkeypatch):
    """Seed minimal dashboard inputs so auth checks fail for auth reasons, not missing files."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    (data_dir / "daily_readiness.csv").write_text(
        "day,score,temperature_deviation,contributors\n"
        "2026-08-01,82,0.1,\"{'hrv_balance': 71, 'resting_heart_rate': 55, 'sleep_balance': 76, 'recovery_index': 74}\"\n",
        encoding="utf-8",
    )
    (data_dir / "daily_sleep.csv").write_text(
        "day,score,contributors\n"
        "2026-08-01,78,\"{'total_sleep': 420, 'efficiency': 90, 'deep_sleep': 82, 'rem_sleep': 71, 'restfulness': 80}\"\n",
        encoding="utf-8",
    )
    (data_dir / "deviation_scores.csv").write_text(
        "day,readiness_score,composite_deviation,z_temperature_deviation,z_hrv_balance,z_resting_heart_rate,z_sleep_balance,flag\n"
        "2026-08-01,82,1.2,0.3,1.1,0.8,0.9,MODERATE\n",
        encoding="utf-8",
    )
    (data_dir / "summaries.jsonl").write_text(
        json.dumps({"date": "2026-08-01", "summary": "**Overall Signal: WATCH**"}) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(api, "DATA_DIR", data_dir)
    monkeypatch.setattr(api, "MODEL_PREDICTION_PATH", data_dir / "model_prediction_latest.json")
    return data_dir


@pytest.fixture
def client(seeded_api_data):
    return TestClient(api.app)


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


SENSITIVE_API_ENDPOINTS = [
    "/api/readiness",
    "/api/sleep",
    "/api/deviation",
    "/api/summary",
    "/api/dashboard",
]


@pytest.mark.parametrize("path", SENSITIVE_API_ENDPOINTS)
def test_dashboard_endpoints_require_auth(client, path):
    """Real-world failure: a third party can read clinical summaries and risk flags without identity checks."""
    response = client.get(path)
    assert response.status_code in {401, 403}


@pytest.mark.parametrize("path", SENSITIVE_API_ENDPOINTS)
def test_dashboard_endpoints_reject_invalid_token(client, path):
    """Real-world failure: forged/expired mobile tokens still yield private health data."""
    response = client.get(path, headers=_auth_headers("invalid-token"))
    assert response.status_code in {401, 403}


def test_dashboard_cors_disallows_untrusted_origin(client):
    """Real-world failure: malicious browser origin can exfiltrate summary and risk data via JS."""
    response = client.options(
        "/api/dashboard",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    allow_origin = response.headers.get("access-control-allow-origin", "")
    assert allow_origin not in {"*", "https://evil.example"}
