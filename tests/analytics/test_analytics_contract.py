from datetime import datetime, timedelta, timezone
from pathlib import Path

import analytics


def _base_event(name: str, session_id: str, timestamp: str) -> dict:
    return {
        "event_name": name,
        "event_version": 1,
        "timestamp_iso": timestamp,
        "distinct_id": "user-1",
        "session_id": session_id,
        "app_version": "0.1.0",
        "platform": "web",
        "env": "ci",
    }


def test_schema_contract_rejects_missing_required_fields():
    """Real-world failure: malformed events silently poison analytics metrics and funnels."""
    event = _base_event("session_started", "s1", datetime.now(timezone.utc).isoformat())
    event.pop("event_version")

    violations = analytics.validate_schema([event])

    assert any("missing required field: event_version" in v for v in violations)


def test_schema_contract_rejects_sensitive_fields():
    """Real-world failure: token or clinical note leakage into telemetry stream."""
    event = _base_event("session_started", "s1", datetime.now(timezone.utc).isoformat())
    event["token"] = "should-not-leave-runtime"

    violations = analytics.validate_schema([event])

    assert any("contains sensitive keys" in v for v in violations)


def test_session_invariant_blocks_completed_without_started():
    """Real-world failure: completion counts inflate despite dropped session-start events."""
    now = datetime.now(timezone.utc)
    events = [
        _base_event("session_completed", "sess-missing-start", (now + timedelta(seconds=1)).isoformat())
    ]

    violations = analytics.validate_session_invariant(events)

    assert any("session_completed without prior session_started" in v for v in violations)


def test_sync_invariant_blocks_completed_without_started():
    """Real-world failure: sync health appears green while sync-start instrumentation is broken."""
    now = datetime.now(timezone.utc)
    events = [
        _base_event("sync_completed", "run-404", (now + timedelta(seconds=1)).isoformat())
    ]

    violations = analytics.validate_sync_invariant(events)

    assert any("sync_completed without prior sync_started" in v for v in violations)


def test_emit_scheduled_canary_writes_valid_contract_events(tmp_path):
    """Real-world failure: scheduled canary job runs but emits unusable analytics payloads."""
    sink = tmp_path / "analytics_events.jsonl"

    assert analytics.emit_event("session_started", "canary", {"source": "schedule"}, sink_path=sink)
    assert analytics.emit_event("sync_started", "canary", {"sync_scope": "full"}, sink_path=sink)
    assert analytics.emit_event("sync_completed", "canary", {"sync_scope": "full", "status": "success"}, sink_path=sink)
    assert analytics.emit_event("session_completed", "canary", {"source": "schedule", "status": "success"}, sink_path=sink)

    events = analytics.load_events(sink)
    schema_violations = analytics.validate_schema(events)
    session_violations = analytics.validate_session_invariant(events)
    sync_violations = analytics.validate_sync_invariant(events)

    assert len(events) == 4
    assert not schema_violations
    assert not session_violations
    assert not sync_violations


def test_html_report_is_written_for_viewing(tmp_path):
    """Real-world failure: CI produces only raw XML, leaving reviewers without a browsable analytics report."""
    sink = tmp_path / "analytics_events.jsonl"
    report = tmp_path / "analytics-report.html"

    analytics.emit_event("session_started", "reportable", {"source": "schedule"}, sink_path=sink)
    analytics.emit_event("session_completed", "reportable", {"source": "schedule", "status": "success"}, sink_path=sink)

    assert analytics.write_html_report(report, sink_path=sink)
    html = report.read_text(encoding="utf-8")

    assert report.exists()
    assert "EMBER Analytics Report" in html
    assert "PASS" in html
    assert "session_started" in html
