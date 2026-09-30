from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import time

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import mood_server


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
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


def _morning_payload() -> dict:
    return {
        "rested": 3,
        "early_waking": "no",
        "less_sleep_fine": "no",
        "thought_speed_morning": 2,
        "classification_night": "normal",
    }


def _backfill_morning_payload() -> dict:
    payload = _morning_payload()
    payload["date"] = "2026-08-01"
    return payload


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {mood_server.API_TOKEN}"}


@pytest.mark.parametrize(
    "path,payload_factory,expected_message",
    [
        ("/submit/morning", _morning_payload, "Morning entry already logged today."),
        ("/submit/backfill/morning", _backfill_morning_payload, "Morning entry already exists for 2026-08-01."),
    ],
)
def test_duplicate_mood_submission_is_atomic(client, isolated_data_dir, monkeypatch, path, payload_factory, expected_message):
    """Real-world failure: two near-simultaneous submissions both pass duplicate check before write."""
    original_write_row = mood_server.write_row

    def slow_write_row(row: dict):
        time.sleep(0.05)
        return original_write_row(row)

    monkeypatch.setattr(mood_server, "write_row", slow_write_row)

    def post_once():
        return client.post(path, json=payload_factory(), headers=_auth_headers())

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: post_once(), range(2)))

    status_codes = sorted(response.status_code for response in responses)
    messages = [response.json().get("message", "") for response in responses]

    assert status_codes == [200, 409]
    assert any(expected_message in message for message in messages)
