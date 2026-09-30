import ast
import json
import sys
import warnings
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from score_baseline import SCORE_METRICS, compute_baseline, flag, score_day

DATA_DIR = ROOT / "data"
GOLDEN_SET_PATH = DATA_DIR / "golden_set_ml_consolidated.csv"
FIXTURES_DIR = ROOT / "tests" / "ml" / "fixtures"
FIXTURE_GOLDEN_SET_PATH = FIXTURES_DIR / "golden_set_ml_consolidated.csv"
FIXTURE_READINESS_PATH = FIXTURES_DIR / "daily_readiness.csv"
REGRESSION_BASELINE_PATH = FIXTURES_DIR / "golden_set_regression_baseline.json"


REQUIRED_GOLDEN_COLUMNS = {
    "source_set",
    "case_id",
    "day",
    "categories",
    "tag_travel_day",
    "tag_unworn_or_partial_wear_day",
    "tag_missing_readiness_contributors",
    "tag_missing_sleep_contributors",
    "tag_api_gap_day_partial_sync",
    "tag_high_deviation_night",
    "tag_normal_recovery_night",
    "has_readiness",
    "has_sleep",
    "has_deviation",
}

REQUIRED_CATEGORY_TAGS = [
    "tag_travel_day",
    "tag_unworn_or_partial_wear_day",
    "tag_missing_readiness_contributors",
    "tag_missing_sleep_contributors",
    "tag_api_gap_day_partial_sync",
    "tag_high_deviation_night",
    "tag_normal_recovery_night",
]


def _load_golden_df() -> pd.DataFrame:
    source = GOLDEN_SET_PATH if GOLDEN_SET_PATH.exists() else FIXTURE_GOLDEN_SET_PATH
    assert source.exists(), f"Missing golden set file: {GOLDEN_SET_PATH} (and fixture: {FIXTURE_GOLDEN_SET_PATH})"
    return pd.read_csv(source)


def _to_int(series: pd.Series) -> pd.Series:
    return series.fillna(0).astype(int)


def _load_readiness_for_scoring() -> pd.DataFrame:
    source = DATA_DIR / "daily_readiness.csv"
    if not source.exists():
        source = FIXTURE_READINESS_PATH
    assert source.exists(), f"Missing readiness file: {DATA_DIR / 'daily_readiness.csv'} (and fixture: {FIXTURE_READINESS_PATH})"

    df = pd.read_csv(source)
    df["day"] = pd.to_datetime(df["day"]).dt.date

    contributors = df["contributors"].apply(ast.literal_eval)
    contrib_df = pd.DataFrame(contributors.tolist())

    out = pd.concat([df[["day", "score", "temperature_deviation"]], contrib_df], axis=1)
    out = out.sort_values("day").reset_index(drop=True)
    return out


def _score_one_day(df: pd.DataFrame, target_day: date) -> dict:
    row = df[df["day"] == target_day]
    assert not row.empty, f"Target day {target_day} not found in readiness data"

    baseline = compute_baseline(df, target_day - timedelta(days=1))
    scored = score_day(row.iloc[0], baseline)
    scored["flag"] = flag(scored["composite_deviation"])
    return scored


def test_golden_set_exists_and_has_required_columns():
    golden = _load_golden_df()
    missing = REQUIRED_GOLDEN_COLUMNS - set(golden.columns)
    assert not missing, f"Golden set missing required columns: {sorted(missing)}"


def test_golden_set_has_real_and_mock_rows():
    golden = _load_golden_df()
    sources = set(golden["source_set"].dropna().unique().tolist())
    assert "real" in sources
    assert "mock" in sources


def test_all_required_category_tags_are_covered_at_least_once():
    golden = _load_golden_df()

    missing_tags = []
    for tag in REQUIRED_CATEGORY_TAGS:
        count = int(_to_int(golden[tag]).sum())
        if count < 1:
            missing_tags.append(tag)

    assert not missing_tags, f"Missing category coverage for tags: {missing_tags}"


def test_mock_scenarios_include_required_gap_missing_sleep_and_high_deviation_cases():
    golden = _load_golden_df()
    mock = golden[golden["source_set"] == "mock"]

    missing_sleep_days = mock[_to_int(mock["tag_missing_sleep_contributors"]) == 1]["day"].tolist()
    api_gap_days = mock[_to_int(mock["tag_api_gap_day_partial_sync"]) == 1]["day"].tolist()
    high_deviation_days = mock[_to_int(mock["tag_high_deviation_night"]) == 1]["day"].tolist()

    assert "2026-07-25" in missing_sleep_days
    assert "2026-07-24" in api_gap_days
    assert "2026-07-27" in high_deviation_days


def test_golden_set_has_no_duplicate_days():
    golden = _load_golden_df().copy()
    normalized_days = pd.to_datetime(golden["day"], errors="coerce")
    assert not normalized_days.isna().any(), "Golden set contains invalid day values"

    golden["day"] = normalized_days.dt.date.astype(str)
    duplicate_mask = golden.duplicated(subset=["source_set", "case_id", "day"], keep=False)
    duplicates = (
        golden.loc[duplicate_mask, ["source_set", "case_id", "day"]]
        .drop_duplicates()
        .to_dict("records")
    )
    assert not duplicates, f"Golden set contains duplicate source_set+case_id+day rows: {duplicates}"


def test_golden_set_has_no_future_dated_rows():
    golden = _load_golden_df().copy()
    normalized_days = pd.to_datetime(golden["day"], errors="coerce")
    assert not normalized_days.isna().any(), "Golden set contains invalid day values"

    today = pd.Timestamp(date.today())
    future_days = normalized_days[normalized_days > today].dt.date.astype(str).unique().tolist()
    assert not future_days, f"Golden set contains future-dated rows: {future_days}"


def test_flag_threshold_boundaries():
    assert flag(None) == "unknown"
    assert flag(0.99) == "NORMAL"
    assert flag(1.0) == "MODERATE"
    assert flag(1.99) == "MODERATE"
    assert flag(2.0) == "HIGH"


def test_strict_causality_future_rows_do_not_change_past_day_score():
    readiness = _load_readiness_for_scoring()

    target_day = date(2026, 7, 10)
    before = _score_one_day(readiness, target_day)

    mutated = readiness.copy()
    future_mask = mutated["day"] > target_day

    for metric in SCORE_METRICS:
        if metric in mutated.columns:
            mutated.loc[future_mask, metric] = 9999.0

    after = _score_one_day(mutated, target_day)

    assert before["composite_deviation"] == after["composite_deviation"]
    assert before["flag"] == after["flag"]

    for metric in SCORE_METRICS:
        key = f"z_{metric}"
        assert before[key] == after[key]


def _current_golden_snapshot(golden: pd.DataFrame) -> dict:
    return {
        "total_rows": int(len(golden)),
        "source_real_rows": int((golden["source_set"] == "real").sum()),
        "source_mock_rows": int((golden["source_set"] == "mock").sum()),
        "rates": {
            "has_readiness": float(_to_int(golden["has_readiness"]).mean()),
            "has_sleep": float(_to_int(golden["has_sleep"]).mean()),
            "has_deviation": float(_to_int(golden["has_deviation"]).mean()),
        },
        "tag_rates": {
            tag: float(_to_int(golden[tag]).mean())
            for tag in REQUIRED_CATEGORY_TAGS
        },
    }


def test_golden_set_regression_threshold_gate_against_frozen_reference():
    """Real-world failure: silent golden-set drift invalidates CI claims without obvious breakage."""
    # Hard gate must be deterministic across local and CI environments.
    # Use the committed fixture snapshot that the frozen baseline is derived from.
    golden = pd.read_csv(FIXTURE_GOLDEN_SET_PATH)
    baseline = json.loads(REGRESSION_BASELINE_PATH.read_text(encoding="utf-8"))

    expected = baseline["expected"]
    threshold = float(baseline["thresholds"]["max_rate_drift"])
    observed = _current_golden_snapshot(golden)

    assert observed["total_rows"] == expected["total_rows"]
    assert observed["source_real_rows"] == expected["source_real_rows"]
    assert observed["source_mock_rows"] == expected["source_mock_rows"]

    for key, expected_value in expected["rates"].items():
        observed_value = observed["rates"][key]
        assert abs(observed_value - expected_value) <= threshold, (
            f"Golden-set rate drift for {key}: observed={observed_value:.4f} "
            f"expected={expected_value:.4f} threshold={threshold:.4f}"
        )

    for key, expected_value in expected["tag_rates"].items():
        observed_value = observed["tag_rates"][key]
        assert abs(observed_value - expected_value) <= threshold, (
            f"Golden-set tag-rate drift for {key}: observed={observed_value:.4f} "
            f"expected={expected_value:.4f} threshold={threshold:.4f}"
        )


def test_golden_set_live_monitor_reports_drift_trends():
    """Real-world monitoring: track live drift trends without blocking merges."""
    golden = _load_golden_df()
    baseline = json.loads(REGRESSION_BASELINE_PATH.read_text(encoding="utf-8"))

    expected = baseline["expected"]
    observed = _current_golden_snapshot(golden)
    soft_threshold = float(baseline.get("thresholds", {}).get("live_monitor_soft_drift", 0.20))

    print(
        "[live-monitor] row_count "
        f"expected={expected['total_rows']} observed={observed['total_rows']} "
        f"delta={observed['total_rows'] - expected['total_rows']}"
    )
    print(
        "[live-monitor] source_mix "
        f"real expected={expected['source_real_rows']} observed={observed['source_real_rows']} | "
        f"mock expected={expected['source_mock_rows']} observed={observed['source_mock_rows']}"
    )

    all_rate_drifts: list[tuple[str, float]] = []
    for key, expected_value in expected["rates"].items():
        observed_value = observed["rates"][key]
        drift = observed_value - expected_value
        all_rate_drifts.append((f"rates.{key}", drift))
        direction = "up" if drift > 0 else "down" if drift < 0 else "flat"
        print(
            f"[live-monitor] rates.{key} expected={expected_value:.4f} "
            f"observed={observed_value:.4f} drift={drift:+.4f} ({direction})"
        )

    for key, expected_value in expected["tag_rates"].items():
        observed_value = observed["tag_rates"][key]
        drift = observed_value - expected_value
        all_rate_drifts.append((f"tag_rates.{key}", drift))
        direction = "up" if drift > 0 else "down" if drift < 0 else "flat"
        print(
            f"[live-monitor] tag_rates.{key} expected={expected_value:.4f} "
            f"observed={observed_value:.4f} drift={drift:+.4f} ({direction})"
        )

    exceeded = [(name, drift) for name, drift in all_rate_drifts if abs(drift) > soft_threshold]
    if exceeded:
        drift_summary = ", ".join(f"{name}={drift:+.4f}" for name, drift in exceeded)
        warnings.warn(
            "Golden-set live monitor drift exceeded soft threshold "
            f"({soft_threshold:.2f}) for: {drift_summary}",
            UserWarning,
        )
