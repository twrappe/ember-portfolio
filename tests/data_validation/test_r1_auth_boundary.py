import csv
import hashlib
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mood_server


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Point mood server storage at an isolated temp directory per test."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(mood_server, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(mood_server, "LOG_FILE", str(data_dir / "mood_log.csv"))
    monkeypatch.setattr(mood_server, "EVENT_FILE", str(data_dir / "events.csv"))
    monkeypatch.setattr(mood_server, "SPIKE_FILE", str(data_dir / "event_spikes.csv"))

    return data_dir


@pytest.fixture
def client(isolated_data_dir):
    return TestClient(mood_server.app)


def _fingerprint(path: Path) -> str:
    if not path.exists():
        return "<missing>"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", newline="") as f:
        return sum(1 for _ in f)


def _morning_payload() -> dict:
    return {
        "rested": 3,
        "early_waking": "no",
        "less_sleep_fine": "no",
        "thought_speed_morning": 2,
        "classification_night": "normal",
    }


def _evening_payload() -> dict:
    return {
        "energy": 3,
        "new_projects": "no",
        "effortful": "no",
        "concentration": 3,
        "mood": 3,
        "irritable": "no",
        "impulsive": "no",
        "withdrew": "no",
        "alcohol": "no",
        "illness": "no",
        "travel": "no",
        "life_stress": "no",
        "classification_day": "normal",
        "notes": "",
    }


def _backfill_morning_payload() -> dict:
    payload = _morning_payload()
    payload["date"] = "2026-08-01"
    return payload


def _backfill_evening_payload() -> dict:
    payload = _evening_payload()
    payload["date"] = "2026-08-01"
    return payload


def _event_payload() -> dict:
    return {
        "name": "Role Change",
        "category": "work",
        "start_date": "2026-08-01",
        "end_date": "",
        "notes": "",
    }


def _event_update_payload() -> dict:
    return {
        "end_date": "2026-08-02",
        "notes": "updated",
    }


def _spike_payload() -> dict:
    return {
        "date": "2026-08-02",
        "severity": 3,
        "notes": "",
    }


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed_event(event_file: Path) -> None:
    event_file.parent.mkdir(parents=True, exist_ok=True)
    with event_file.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=mood_server.EVENT_FIELDS)
        writer.writeheader()
        writer.writerow(
            {
                "id": 1,
                "name": "Seeded",
                "category": "other",
                "start_date": "2026-08-01",
                "end_date": "",
                "notes": "",
            }
        )


SENSITIVE_ENDPOINTS = [
    ("post", "/submit/morning", _morning_payload),
    ("post", "/submit/evening", _evening_payload),
    ("post", "/submit/backfill/morning", _backfill_morning_payload),
    ("post", "/submit/backfill/evening", _backfill_evening_payload),
    ("get", "/history", None),
    ("post", "/events", _event_payload),
    ("get", "/events", None),
    ("get", "/events/1", None),
    ("patch", "/events/1", _event_update_payload),
    ("post", "/events/1/spikes", _spike_payload),
    ("get", "/events/1/spikes", None),
]


@pytest.mark.parametrize("method,path,payload_factory", SENSITIVE_ENDPOINTS)
def test_sensitive_endpoints_require_auth(client, isolated_data_dir, method, path, payload_factory):
    event_file = isolated_data_dir / "events.csv"
    _seed_event(event_file)

    request = getattr(client, method)
    kwargs = {}
    if payload_factory is not None:
        kwargs["json"] = payload_factory()

    response = request(path, **kwargs)

    assert response.status_code in {401, 403}


@pytest.mark.parametrize("method,path,payload_factory", SENSITIVE_ENDPOINTS)
def test_sensitive_endpoints_reject_invalid_token(client, isolated_data_dir, method, path, payload_factory):
    event_file = isolated_data_dir / "events.csv"
    _seed_event(event_file)

    request = getattr(client, method)
    kwargs = {"headers": _auth_headers("definitely-not-valid")}
    if payload_factory is not None:
        kwargs["json"] = payload_factory()

    response = request(path, **kwargs)

    assert response.status_code in {401, 403}


def test_cors_disallows_untrusted_origin_for_sensitive_route(client):
    response = client.options(
        "/submit/morning",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    allow_origin = response.headers.get("access-control-allow-origin", "")
    assert allow_origin not in {"*", "https://evil.example"}


def test_unauth_mood_write_does_not_mutate_storage(client, isolated_data_dir):
    log_file = isolated_data_dir / "mood_log.csv"
    before_hash = _fingerprint(log_file)
    before_lines = _line_count(log_file)

    response = client.post("/submit/morning", json=_morning_payload())

    after_hash = _fingerprint(log_file)
    after_lines = _line_count(log_file)

    assert response.status_code in {401, 403}
    assert after_hash == before_hash
    assert after_lines == before_lines


def test_unauth_event_write_does_not_mutate_storage(client, isolated_data_dir):
    event_file = isolated_data_dir / "events.csv"
    spike_file = isolated_data_dir / "event_spikes.csv"

    _seed_event(event_file)

    event_before_hash = _fingerprint(event_file)
    event_before_lines = _line_count(event_file)
    spike_before_hash = _fingerprint(spike_file)
    spike_before_lines = _line_count(spike_file)

    create_event_response = client.post("/events", json=_event_payload())
    create_spike_response = client.post("/events/1/spikes", json=_spike_payload())

    event_after_hash = _fingerprint(event_file)
    event_after_lines = _line_count(event_file)
    spike_after_hash = _fingerprint(spike_file)
    spike_after_lines = _line_count(spike_file)

    assert create_event_response.status_code in {401, 403}
    assert create_spike_response.status_code in {401, 403}
    assert event_after_hash == event_before_hash
    assert event_after_lines == event_before_lines
    assert spike_after_hash == spike_before_hash
    assert spike_after_lines == spike_before_lines
