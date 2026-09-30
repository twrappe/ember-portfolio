import pandas as pd

import pull_data


def test_partial_sync_resumes_from_first_missing_day(tmp_path, monkeypatch):
    """Real-world failure prevented: crash between readiness and sleep should resume from the first missing day."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    readiness = pd.DataFrame(
        {
            "day": ["2026-08-01", "2026-08-02", "2026-08-03"],
            "score": [80, 81, 82],
        }
    )
    sleep = pd.DataFrame(
        {
            "day": ["2026-08-01"],
            "score": [75],
        }
    )

    readiness.to_csv(data_dir / "daily_readiness.csv", index=False)
    sleep.to_csv(data_dir / "daily_sleep.csv", index=False)

    monkeypatch.setattr(pull_data, "DATA_DIR", str(data_dir))

    start = pull_data.get_start_date("daily_sleep")

    assert start == "2026-08-02", (
        "Expected resume from first missing sleep day after a mid-run crash; "
        "otherwise pipeline can skip data permanently."
    )
