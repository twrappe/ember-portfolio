from pathlib import Path

import pytest

import model_logreg
import score_baseline


def test_baseline_scoring_handles_malformed_contributors(tmp_path, monkeypatch):
    """Real-world failure: one bad contributor payload halts scoring for every day after ingestion."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    (data_dir / "daily_readiness.csv").write_text(
        "day,score,temperature_deviation,contributors\n"
        "2026-08-01,80,0.1,not-a-dict\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(score_baseline, "DATA_DIR", str(data_dir))
    df = score_baseline.load_readiness()

    assert not df.empty


def test_model_feature_loading_handles_malformed_contributors(tmp_path, monkeypatch):
    """Real-world failure: one malformed contributors field blocks model retraining and daily prediction."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    (data_dir / "daily_readiness.csv").write_text(
        "day,score,temperature_deviation,contributors\n"
        "2026-08-01,82,0.2,broken\n",
        encoding="utf-8",
    )
    (data_dir / "daily_sleep.csv").write_text(
        "day,score,contributors\n"
        "2026-08-01,77,broken\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(model_logreg, "DATA_DIR", Path(data_dir))
    readiness = model_logreg.load_readiness()
    sleep = model_logreg.load_sleep()

    assert not readiness.empty
    assert not sleep.empty
