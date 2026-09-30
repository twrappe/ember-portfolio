import json
import os
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVENT_SINK_PATH = Path(os.getenv("ANALYTICS_SINK_PATH", "data/analytics_events.jsonl"))
APP_VERSION = os.getenv("APP_VERSION", "dev")
ANALYTICS_ENV = os.getenv("EMBER_ENV", "dev")
PLATFORM = os.getenv("ANALYTICS_PLATFORM", "backend")
DISTINCT_ID = os.getenv("ANALYTICS_DISTINCT_ID", "local-user")

REQUIRED_FIELDS = {
    "event_name": str,
    "event_version": int,
    "timestamp_iso": str,
    "distinct_id": str,
    "session_id": str,
    "app_version": str,
    "platform": str,
    "env": str,
}

ALLOWED_EVENT_NAMES = {
    "session_started",
    "session_completed",
    "sync_started",
    "sync_completed",
    "checkin_submitted",
    "alert_viewed",
    "alert_acknowledged",
    "prediction_rendered",
    "prediction_journal_agreement_computed",
}

SENSITIVE_KEYS = {
    "oura_access_token",
    "oura_refresh_token",
    "token",
    "authorization",
    "notes",
    "raw_biometrics",
}

FAULT_INJECTION_MODES = {
    "sensitive_key",
    "missing_event_version",
    "unknown_event_name",
    "orphan_sync_completed",
    "all",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit_event(
    event_name: str,
    session_id: str,
    properties: dict[str, Any] | None = None,
    *,
    event_version: int = 1,
    sink_path: Path | None = None,
) -> bool:
    """Write a single analytics event to the local sink. Non-blocking on failure."""
    target = sink_path or EVENT_SINK_PATH
    event = {
        "event_name": event_name,
        "event_version": event_version,
        "timestamp_iso": _utc_now_iso(),
        "distinct_id": DISTINCT_ID,
        "session_id": session_id,
        "app_version": APP_VERSION,
        "platform": PLATFORM,
        "env": ANALYTICS_ENV,
    }
    if properties:
        event.update(properties)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=True) + "\n")
        return True
    except Exception:
        # Analytics must never block product flows.
        return False


def _write_raw_event(event: dict[str, Any], sink_path: Path | None = None) -> bool:
    """Write a raw event payload for fault-injection scenarios."""
    target = sink_path or EVENT_SINK_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=True) + "\n")
        return True
    except Exception:
        return False


def load_events(sink_path: Path | None = None) -> list[dict[str, Any]]:
    target = sink_path or EVENT_SINK_PATH
    if not target.exists():
        return []

    rows: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def validate_schema(events: list[dict[str, Any]]) -> list[str]:
    violations: list[str] = []

    for i, event in enumerate(events):
        for field, expected_type in REQUIRED_FIELDS.items():
            if field not in event:
                violations.append(f"event[{i}] missing required field: {field}")
                continue
            if not isinstance(event[field], expected_type):
                violations.append(
                    f"event[{i}] field {field} expected {expected_type.__name__}, got {type(event[field]).__name__}"
                )

        name = event.get("event_name")
        if name not in ALLOWED_EVENT_NAMES:
            violations.append(f"event[{i}] unknown event_name: {name}")

        lower_keys = {str(k).lower() for k in event.keys()}
        leaked = sorted(SENSITIVE_KEYS.intersection(lower_keys))
        if leaked:
            violations.append(f"event[{i}] contains sensitive keys: {leaked}")

    return violations


def validate_session_invariant(events: list[dict[str, Any]]) -> list[str]:
    """session_completed must not exist without a prior session_started for the same session_id."""
    violations: list[str] = []
    started: set[str] = set()

    ordered = sorted(events, key=lambda e: str(e.get("timestamp_iso", "")))
    for event in ordered:
        name = event.get("event_name")
        session_id = str(event.get("session_id", ""))

        if name == "session_started":
            started.add(session_id)
        elif name == "session_completed" and session_id not in started:
            violations.append(
                f"session_completed without prior session_started for session_id={session_id}"
            )

    return violations


def validate_sync_invariant(events: list[dict[str, Any]]) -> list[str]:
    """sync_completed must not exist without a prior sync_started for same session/run id."""
    violations: list[str] = []
    started: set[str] = set()

    ordered = sorted(events, key=lambda e: str(e.get("timestamp_iso", "")))
    for event in ordered:
        name = event.get("event_name")
        session_id = str(event.get("session_id", ""))

        if name == "sync_started":
            started.add(session_id)
        elif name == "sync_completed" and session_id not in started:
            violations.append(
                f"sync_completed without prior sync_started for session_id={session_id}"
            )

    return violations


def emit_scheduled_canary(session_id: str = "scheduled-canary", sink_path: Path | None = None) -> bool:
    ok1 = emit_event("session_started", session_id, {"source": "schedule"}, sink_path=sink_path)
    ok2 = emit_event("sync_started", session_id, {"sync_scope": "full"}, sink_path=sink_path)
    ok3 = emit_event("sync_completed", session_id, {"sync_scope": "full", "status": "success"}, sink_path=sink_path)
    ok4 = emit_event("session_completed", session_id, {"source": "schedule", "status": "success"}, sink_path=sink_path)
    return all([ok1, ok2, ok3, ok4])


def emit_fault_injection(mode: str, sink_path: Path | None = None) -> bool:
    """Emit intentionally bad analytics payloads for red-gate validation."""
    if mode not in FAULT_INJECTION_MODES:
        return False

    session_id = f"fault-injection-{mode}"
    base = {
        "event_name": "sync_started",
        "event_version": 1,
        "timestamp_iso": _utc_now_iso(),
        "distinct_id": DISTINCT_ID,
        "session_id": session_id,
        "app_version": APP_VERSION,
        "platform": PLATFORM,
        "env": ANALYTICS_ENV,
    }

    if mode == "sensitive_key":
        return emit_event(
            "sync_completed",
            session_id,
            {
                "sync_scope": "full",
                "status": "success",
                "source": "fault_injection",
                "token": "LEAKED_TEST_TOKEN",
            },
            sink_path=sink_path,
        )

    if mode == "missing_event_version":
        raw = dict(base)
        raw.pop("event_version", None)
        return _write_raw_event(raw, sink_path=sink_path)

    if mode == "unknown_event_name":
        return emit_event(
            "sync_mystery_state",
            session_id,
            {"source": "fault_injection"},
            sink_path=sink_path,
        )

    if mode == "orphan_sync_completed":
        return emit_event(
            "sync_completed",
            session_id,
            {
                "sync_scope": "full",
                "status": "success",
                "source": "fault_injection",
            },
            sink_path=sink_path,
        )

    # mode == "all"
    ok1 = emit_fault_injection("sensitive_key", sink_path=sink_path)
    ok2 = emit_fault_injection("missing_event_version", sink_path=sink_path)
    ok3 = emit_fault_injection("unknown_event_name", sink_path=sink_path)
    ok4 = emit_fault_injection("orphan_sync_completed", sink_path=sink_path)
    return all([ok1, ok2, ok3, ok4])


def collect_violations(events: list[dict[str, Any]]) -> list[str]:
    return (
        validate_schema(events)
        + validate_session_invariant(events)
        + validate_sync_invariant(events)
    )


def run_green_gate(sink_path: Path | None = None) -> tuple[bool, list[str], Path]:
    """Emit valid canary events in a clean sink and validate for a deterministic green gate."""
    target = sink_path or (EVENT_SINK_PATH.parent / "analytics_green_gate.jsonl")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")

    if not emit_scheduled_canary(session_id="green-gate-canary", sink_path=target):
        return False, ["failed to emit scheduled canary events"], target

    events = load_events(target)
    violations = collect_violations(events)
    return len(violations) == 0, violations, target


def _html_escape(value: Any) -> str:
        text = str(value)
        return (
                text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;")
        )


def render_html_report(events: list[dict[str, Any]], violations: list[str]) -> str:
        schema_violations = validate_schema(events)
        session_violations = validate_session_invariant(events)
        sync_violations = validate_sync_invariant(events)
        all_violations = violations + schema_violations + session_violations + sync_violations

        event_counts: dict[str, int] = {}
        for event in events:
                name = str(event.get("event_name", "unknown"))
                event_counts[name] = event_counts.get(name, 0) + 1

        def list_items(items: list[str]) -> str:
                if not items:
                        return "<li>None</li>"
                return "".join(f"<li>{_html_escape(item)}</li>" for item in items)

        rows = "".join(
                f"<tr><td>{_html_escape(name)}</td><td>{count}</td></tr>"
                for name, count in sorted(event_counts.items())
        ) or "<tr><td colspan='2'>No events captured</td></tr>"

        status = "PASS" if not all_violations else "FAIL"

        return f"""<!doctype html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>EMBER Analytics Report</title>
    <style>
        body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 24px; color: #111827; background: #f9fafb; }}
        .card {{ background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px 20px; margin-bottom: 16px; box-shadow: 0 1px 2px rgba(0,0,0,.04); }}
        h1, h2 {{ margin: 0 0 12px 0; }}
        .status {{ font-weight: 700; font-size: 18px; }}
        .pass {{ color: #047857; }}
        .fail {{ color: #b91c1c; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #e5e7eb; }}
        code {{ background: #eef2ff; padding: 2px 4px; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class=\"card\">
        <h1>EMBER Analytics Report</h1>
        <div class=\"status {"pass" if status == "PASS" else "fail"}\">Status: {status}</div>
        <div>Generated: {_html_escape(_utc_now_iso())}</div>
        <div>Events captured: {len(events)}</div>
    </div>

    <div class=\"card\">
        <h2>Event Counts</h2>
        <table>
            <thead><tr><th>Event</th><th>Count</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>

    <div class=\"card\">
        <h2>Schema Violations</h2>
        <ul>{list_items(schema_violations)}</ul>
    </div>

    <div class=\"card\">
        <h2>Session Invariant Violations</h2>
        <ul>{list_items(session_violations)}</ul>
    </div>

    <div class=\"card\">
        <h2>Sync Invariant Violations</h2>
        <ul>{list_items(sync_violations)}</ul>
    </div>

    <div class=\"card\">
        <h2>Extra Violations</h2>
        <ul>{list_items(violations)}</ul>
    </div>
</body>
</html>"""


def write_html_report(output_path: Path, sink_path: Path | None = None, violations: list[str] | None = None) -> bool:
        try:
                events = load_events(sink_path)
                html = render_html_report(events, violations or [])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(html, encoding="utf-8")
                return True
        except Exception:
                return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=str, help="Write an HTML analytics report to this path")
    parser.add_argument("--sink", type=str, help="Analytics sink path to read/write")
    parser.add_argument(
        "--inject-fault",
        type=str,
        choices=sorted(FAULT_INJECTION_MODES),
        help="Emit intentionally bad analytics event(s) for red-gate testing",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate sink and print violations",
    )
    parser.add_argument(
        "--fail-on-violations",
        action="store_true",
        help="Exit non-zero when validation finds violations",
    )
    parser.add_argument(
        "--green-gate",
        action="store_true",
        help="Run deterministic green gate: emit valid canary events in clean sink and validate",
    )
    args = parser.parse_args()

    sink_override = Path(args.sink) if args.sink else None

    if args.green_gate:
        ok, violations, target = run_green_gate(sink_override)
        print(f"Green gate sink: {target}")
        if violations:
            for violation in violations:
                print(violation)
            raise SystemExit(1)
        print("GREEN_GATE_PASS")
        raise SystemExit(0)

    if args.inject_fault:
        if not emit_fault_injection(args.inject_fault, sink_path=sink_override):
            raise SystemExit(1)
        print(f"Injected analytics fault mode: {args.inject_fault}")

    if args.validate:
        events = load_events(sink_override)
        violations = collect_violations(events)
        if violations:
            for violation in violations:
                print(violation)
        else:
            print("NO_VIOLATIONS")
        if args.fail_on_violations and violations:
            raise SystemExit(1)

    elif args.report:
        report_path = Path(args.report)
        if not write_html_report(report_path, sink_path=sink_override):
            raise SystemExit(1)
        print(f"Analytics HTML report written to {report_path}")

    elif not args.inject_fault:
        target = sink_override or EVENT_SINK_PATH
        if not emit_scheduled_canary(sink_path=target):
            raise SystemExit(1)
        print(f"Canary analytics events written to {target}")

        # Default canary path is now also a gate: fail if sink has any contract violations.
        events = load_events(target)
        violations = collect_violations(events)
        if violations:
            for violation in violations:
                print(violation)
            raise SystemExit(1)
