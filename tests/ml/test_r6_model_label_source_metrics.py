from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import model_logreg


def _frame() -> pd.DataFrame:
    rows = []
    for idx, source in enumerate(("mood", "mood", "mood", "oura", "oura", "oura")):
        rows.append(
            {
                "hrv_balance": 40 + idx,
                "rhr": 55 + idx,
                "temp_deviation": 0.1 + idx * 0.01,
                "sleep_score": 70 + idx,
                "deep_sleep_pct": 20 + idx,
                "rem_pct": 30 + idx,
                "label": idx % 2,
                "label_source": source,
            }
        )
    return pd.DataFrame(rows)


def test_label_source_metrics_are_reported_separately(monkeypatch):
    """Real-world failure: blended metrics hide whether journal labels and Oura fallback diverge."""
    calls = []

    def fake_evaluate_loocv(X, y):
        calls.append((len(X), int(sum(y))))
        return {
            "accuracy": 0.75,
            "roc_auc": 0.88,
            "report_dict": {
                "elevated": {"recall": 0.8, "precision": 0.7},
                "baseline": {"recall": 0.9, "precision": 0.8},
            },
        }

    monkeypatch.setattr(model_logreg, "evaluate_loocv", fake_evaluate_loocv)

    summary = model_logreg.evaluate_label_source_metrics(_frame())

    assert len(calls) == 3
    assert calls[0][0] == 6
    assert calls[1][0] == 3
    assert calls[2][0] == 3
    assert summary["overall"]["accuracy"] == 0.75
    assert summary["by_source"]["mood"]["status"] == "ok"
    assert summary["by_source"]["oura"]["status"] == "ok"
    assert summary["by_source"]["mood"]["n"] == 3
    assert summary["by_source"]["oura"]["n"] == 3
