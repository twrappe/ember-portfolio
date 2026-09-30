import pandas as pd

import pull_data


def test_repull_correction_overwrites_stale_row(tmp_path, monkeypatch):
    """Real-world failure: corrected Oura history is dropped, preserving wrong baseline inputs."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    existing = pd.DataFrame(
        {
            "day": ["2026-08-01"],
            "score": [70],
        }
    )
    corrected = pd.DataFrame(
        {
            "day": ["2026-08-01"],
            "score": [85],
        }
    )

    existing.to_csv(data_dir / "daily_readiness.csv", index=False)

    monkeypatch.setattr(pull_data, "DATA_DIR", str(data_dir))
    pull_data.save(corrected, "daily_readiness")

    merged = pd.read_csv(data_dir / "daily_readiness.csv")
    observed = int(merged.loc[merged["day"] == "2026-08-01", "score"].iloc[0])

    assert observed == 85, "Newest corrected Oura row should win for the same day."


def test_save_rejects_future_dated_rows(tmp_path, monkeypatch):
    """Real-world failure: future rows should fail fast instead of entering scoring inputs."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    incoming = pd.DataFrame(
        {
            "day": ["2099-12-31"],
            "score": [85],
        }
    )

    monkeypatch.setattr(pull_data, "DATA_DIR", str(data_dir))

    try:
        pull_data.save(incoming, "daily_readiness")
        raise AssertionError("Expected save() to reject future-dated rows")
    except ValueError as exc:
        assert "future-dated" in str(exc)
