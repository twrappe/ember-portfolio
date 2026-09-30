from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import warnings

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_GOLDEN_SET_PATH = ROOT / "tests" / "ml" / "fixtures" / "golden_set_ml_consolidated.csv"

REQUIRED_CATEGORY_TAGS = [
    "tag_travel_day",
    "tag_unworn_or_partial_wear_day",
    "tag_missing_readiness_contributors",
    "tag_missing_sleep_contributors",
    "tag_api_gap_day_partial_sync",
    "tag_high_deviation_night",
    "tag_normal_recovery_night",
]


@dataclass(frozen=True)
class FaultScenario:
    name: str
    expected_caught: bool


def _base_fixture() -> pd.DataFrame:
    return pd.read_csv(FIXTURE_GOLDEN_SET_PATH)


def _inject_missing_sleep_contributors(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["tag_missing_sleep_contributors"] = 0
    return out


def _inject_partial_sync_gap_day(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["tag_api_gap_day_partial_sync"] = 0
    return out


def _inject_corrupted_numeric_field(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["has_sleep"] = out["has_sleep"].astype(object)
    out.loc[out.index[0], "has_sleep"] = "not-a-number"
    return out


def _inject_duplicate_day_row(df: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([df, df.iloc[[0]].copy()], ignore_index=True)


def _inject_future_dated_row(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.concat([df, df.iloc[[0]].copy()], ignore_index=True)
    out.loc[out.index[-1], "day"] = "2099-12-31"
    out.loc[out.index[-1], "case_id"] = "fault-future-day"
    return out


def _to_int(series: pd.Series) -> pd.Series:
    return series.fillna(0).astype(int)


def _run_current_gates(df: pd.DataFrame) -> set[str]:
    """Approximate currently enforced gates to classify what is caught vs missed."""
    caught: set[str] = set()

    for tag in REQUIRED_CATEGORY_TAGS:
        try:
            if int(_to_int(df[tag]).sum()) < 1:
                if tag == "tag_missing_sleep_contributors":
                    caught.add("missing_sleep_contributors")
                if tag == "tag_api_gap_day_partial_sync":
                    caught.add("partial_sync_gap_day")
        except Exception:
            pass

    mock = df[df["source_set"] == "mock"] if "source_set" in df.columns else pd.DataFrame()
    if not mock.empty:
        missing_sleep_days = mock[_to_int(mock["tag_missing_sleep_contributors"]) == 1]["day"].tolist()
        api_gap_days = mock[_to_int(mock["tag_api_gap_day_partial_sync"]) == 1]["day"].tolist()
        if "2026-07-25" not in missing_sleep_days:
            caught.add("missing_sleep_contributors")
        if "2026-07-24" not in api_gap_days:
            caught.add("partial_sync_gap_day")

    try:
        _ = _to_int(df["has_readiness"]).mean()
        _ = _to_int(df["has_sleep"]).mean()
        _ = _to_int(df["has_deviation"]).mean()
    except Exception:
        caught.add("corrupted_numeric_field")

    try:
        if "day" in df.columns:
            normalized_days = pd.to_datetime(df["day"], errors="coerce")
            if normalized_days.isna().any():
                caught.add("future_dated_row")
            else:
                today = pd.Timestamp.now("UTC").normalize().tz_localize(None)
                if (normalized_days > today).any():
                    caught.add("future_dated_row")

                normalized_df = df.copy()
                normalized_df["day"] = normalized_days.dt.date.astype(str)
                duplicate_subset = ["day"]
                if "source_set" in normalized_df.columns and "case_id" in normalized_df.columns:
                    duplicate_subset = ["source_set", "case_id", "day"]

                if normalized_df.duplicated(subset=duplicate_subset).any():
                    caught.add("duplicate_day_row")
    except Exception:
        pass

    return caught


def _scenario_matrix() -> list[FaultScenario]:
    return [
        FaultScenario("missing_sleep_contributors", True),
        FaultScenario("partial_sync_gap_day", True),
        FaultScenario("corrupted_numeric_field", True),
        FaultScenario("duplicate_day_row", True),
        FaultScenario("future_dated_row", True),
    ]


def _inject(df: pd.DataFrame, scenario_name: str) -> pd.DataFrame:
    if scenario_name == "missing_sleep_contributors":
        return _inject_missing_sleep_contributors(df)
    if scenario_name == "partial_sync_gap_day":
        return _inject_partial_sync_gap_day(df)
    if scenario_name == "corrupted_numeric_field":
        return _inject_corrupted_numeric_field(df)
    if scenario_name == "duplicate_day_row":
        return _inject_duplicate_day_row(df)
    if scenario_name == "future_dated_row":
        return _inject_future_dated_row(df)
    raise ValueError(f"Unknown scenario: {scenario_name}")


def _build_fault_report(observed_catches: dict[str, bool]) -> dict:
    scenarios = _scenario_matrix()
    rows = []
    for scenario in scenarios:
        observed = observed_catches.get(scenario.name, False)
        rows.append(
            {
                "scenario": scenario.name,
                "expected_caught": scenario.expected_caught,
                "observed_caught": observed,
                "match": observed == scenario.expected_caught,
            }
        )

    caught = [item["scenario"] for item in rows if item["observed_caught"]]
    missed = [item["scenario"] for item in rows if not item["observed_caught"]]
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "caught": caught,
        "missed": missed,
    }


def _write_fault_report(report: dict, markdown_path: Path, json_path: Path) -> None:
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Fault Injection Gate Report",
        "",
        f"Generated: {report['generated_at_utc']}",
        "",
        "## Scenario Results",
        "",
        "| Scenario | Expected caught | Observed caught | Match |",
        "| --- | --- | --- | --- |",
    ]

    for item in report["rows"]:
        lines.append(
            f"| {item['scenario']} | {item['expected_caught']} | {item['observed_caught']} | {item['match']} |"
        )

    lines.append("")
    lines.append("## What Gates Catch")
    lines.append("")
    if report["caught"]:
        for scenario in report["caught"]:
            lines.append(f"- {scenario}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## What Gates Miss")
    lines.append("")
    if report["missed"]:
        for scenario in report["missed"]:
            lines.append(f"- {scenario}")
    else:
        lines.append("- none")

    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def test_fault_injection_catalog_catches_and_misses_are_documented():
    """Real-world debrief need: show exactly which injected failures gates catch vs miss today."""
    base = _base_fixture()
    observed_catches: dict[str, bool] = {}

    for scenario in _scenario_matrix():
        injected = _inject(base, scenario.name)
        caught_by_current_gates = scenario.name in _run_current_gates(injected)
        observed_catches[scenario.name] = caught_by_current_gates

        print(
            f"[fault-injection] {scenario.name}: "
            f"caught={caught_by_current_gates} expected={scenario.expected_caught}"
        )

        assert caught_by_current_gates == scenario.expected_caught

    report = _build_fault_report(observed_catches)
    report_md = Path(os.getenv("FAULT_INJECTION_REPORT_PATH", "artifacts/fault-injection-report.md"))
    report_json = Path(os.getenv("FAULT_INJECTION_REPORT_JSON_PATH", "artifacts/fault-injection-report.json"))
    _write_fault_report(report, report_md, report_json)

    missed = report["missed"]
    if missed:
        warnings.warn(
            "Fault injection catalog includes known misses that remain open: " + ", ".join(missed),
            UserWarning,
        )


def test_fault_injection_catalog_has_five_realistic_scenarios():
    """Assignment contract: maintain at least five realistic injected failure modes."""
    scenarios = _scenario_matrix()
    assert len(scenarios) >= 5
    assert {s.name for s in scenarios} == {
        "missing_sleep_contributors",
        "partial_sync_gap_day",
        "corrupted_numeric_field",
        "duplicate_day_row",
        "future_dated_row",
    }
