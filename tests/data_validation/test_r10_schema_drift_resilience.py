from pathlib import Path

import pytest

import model_logreg


def test_model_handles_missing_contributor_keys(tmp_path, monkeypatch):
    """Real-world failure: upstream Oura schema drift crashes feature extraction mid-run."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    (data_dir / "daily_readiness.csv").write_text(
        "day,score,temperature_deviation,contributors\n"
        "2026-08-01,82,0.2,\"{'resting_heart_rate': 54}\"\n",
        encoding="utf-8",
    )
    (data_dir / "daily_sleep.csv").write_text(
        "day,score,contributors\n"
        "2026-08-01,77,\"{'rem_sleep': 68}\"\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(model_logreg, "DATA_DIR", Path(data_dir))

    readiness = model_logreg.load_readiness()
    sleep = model_logreg.load_sleep()

    assert "hrv_balance" in readiness.columns
    assert "deep_sleep_pct" in sleep.columns
