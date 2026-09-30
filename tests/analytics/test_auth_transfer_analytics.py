import json

import pytest
import requests

import analytics
import pull_data
import token_manager


def _events_from_calls(calls):
    out = []
    for name, session_id, properties in calls:
        event = {
            "event_name": name,
            "event_version": 1,
            "timestamp_iso": "2026-01-01T00:00:00+00:00",
            "distinct_id": "ci-user",
            "session_id": session_id,
            "app_version": "ci",
            "platform": "backend",
            "env": "ci",
        }
        if properties:
            event.update(properties)
        out.append(event)
    return out


def _assert_no_token_value_leak(calls, sensitive_values):
    blob = json.dumps(calls)
    for value in sensitive_values:
        assert value not in blob


def test_fetch_emits_sync_started_and_completed_on_success(monkeypatch):
    """Real-world failure: ingest succeeds but analytics cannot prove transfer occurred."""
    calls = []

    def fake_emit(name, session_id, properties=None, **_kwargs):
        calls.append((name, session_id, properties or {}))
        return True

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"day": "2026-08-01"}]}

    monkeypatch.setattr(pull_data, "emit_event", fake_emit)
    monkeypatch.setattr(pull_data.requests, "get", lambda *args, **kwargs: FakeResp())

    token = "top-secret-access-token"
    rows = pull_data.fetch("daily_readiness", token, "2026-08-01")

    assert rows == [{"day": "2026-08-01"}]
    assert calls[0][0] == "sync_started"
    assert calls[1][0] == "sync_completed"
    assert calls[1][2]["status"] == "success"

    _assert_no_token_value_leak(calls, [token])
    schema_violations = analytics.validate_schema(_events_from_calls(calls))
    assert not schema_violations


def test_fetch_emits_error_completion_on_failure(monkeypatch):
    """Real-world failure: failed transfer is invisible, masking ingest outage in QA telemetry."""
    calls = []

    def fake_emit(name, session_id, properties=None, **_kwargs):
        calls.append((name, session_id, properties or {}))
        return True

    class FakeResp:
        status_code = 500

        def raise_for_status(self):
            raise requests.HTTPError("boom")

        def json(self):
            return {"data": []}

    monkeypatch.setattr(pull_data, "emit_event", fake_emit)
    monkeypatch.setattr(pull_data.requests, "get", lambda *args, **kwargs: FakeResp())

    with pytest.raises(requests.HTTPError):
        pull_data.fetch("daily_sleep", "access-token", "2026-08-01")

    assert calls[0][0] == "sync_started"
    assert calls[-1][0] == "sync_completed"
    assert calls[-1][2]["status"] == "error"
    schema_violations = analytics.validate_schema(_events_from_calls(calls))
    assert not schema_violations


def test_token_validation_emits_auth_sync_events_without_token_leak(monkeypatch):
    """Real-world failure: auth gate emits success but accidentally logs bearer token value."""
    calls = []

    def fake_emit(name, session_id, properties=None, **_kwargs):
        calls.append((name, session_id, properties or {}))
        return True

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

    monkeypatch.setattr(token_manager, "emit_event", fake_emit)
    monkeypatch.setattr(token_manager.requests, "get", lambda *args, **kwargs: FakeResp())

    monkeypatch.setenv("OURA_ACCESS_TOKEN", "real-access-token")
    monkeypatch.setenv("OURA_REFRESH_TOKEN", "real-refresh-token")

    token = token_manager.get_valid_token()

    assert token == "real-access-token"
    assert calls[0][0] == "sync_started"
    assert calls[1][0] == "sync_completed"
    assert calls[1][2]["status"] == "success"
    assert calls[1][2]["path"] == "valid_access_token"

    _assert_no_token_value_leak(calls, ["real-access-token", "real-refresh-token"])
    schema_violations = analytics.validate_schema(_events_from_calls(calls))
    assert not schema_violations
