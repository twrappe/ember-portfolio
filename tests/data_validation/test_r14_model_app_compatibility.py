import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import api
import model_logreg


def _valid_prediction_payload() -> dict:
    return {
        "day": "2026-08-18",
        "prediction": "ELEVATED",
        "p_elevated": 0.72,
        "model": "logreg_stress",
        "explanation": [
            {
                "feature": "hrv_balance",
                "raw": 52.0,
                "z": -1.1,
                "coef": -0.24,
                "contribution": 0.26,
                "direction": "toward_elevated",
            }
        ],
    }


def _valid_manifest_payload() -> dict:
    return {
        "active_model": "models/logreg_stress.joblib",
        "active_metrics": {
            "accuracy": 0.8,
            "roc_auc": 0.85,
            "elevated_recall": 0.78,
            "elevated_precision": 0.75,
            "baseline_recall": 0.82,
        },
        "history": [
            {
                "version": "20260818T120000Z",
                "artifact": "models/logreg_stress_20260818T120000Z.joblib",
                "metrics": {
                    "accuracy": 0.8,
                    "roc_auc": 0.85,
                    "elevated_recall": 0.78,
                    "elevated_precision": 0.75,
                    "baseline_recall": 0.82,
                },
                "source_metrics": {
                    "overall": {"accuracy": 0.8},
                    "by_source": {
                        "mood": {"n": 8, "status": "ok"},
                        "oura": {"n": 22, "status": "ok"},
                    },
                },
                "label_source_counts": {"mood": 8, "oura": 22},
                "dataset_size": 30,
                "promotion_decision": "promoted",
                "decision_reason": "passed",
            }
        ],
    }


def test_model_prediction_contract_matches_frontend_fields():
    """Real-world failure: app expects model fields that silently disappear after model code changes."""
    assert api.is_model_prediction_compatible(_valid_prediction_payload())



def test_model_prediction_contract_rejects_incompatible_shape():
    """Real-world failure: malformed model payload reaches dashboard and breaks check-in rendering."""
    invalid = _valid_prediction_payload()
    invalid.pop("p_elevated")

    assert not api.is_model_prediction_compatible(invalid)



def test_api_get_model_prediction_enforces_contract(tmp_path, monkeypatch):
    """Real-world failure: invalid JSON payload is served directly to frontend without schema guard."""
    prediction_path = tmp_path / "model_prediction_latest.json"
    monkeypatch.setattr(api, "MODEL_PREDICTION_PATH", prediction_path)

    prediction_path.write_text(json.dumps(_valid_prediction_payload()), encoding="utf-8")
    assert api.get_model_prediction() is not None

    prediction_path.write_text(json.dumps({"prediction": "ELEVATED"}), encoding="utf-8")
    assert api.get_model_prediction() is None



def test_model_manifest_contract_roundtrip(tmp_path, monkeypatch):
    """Real-world failure: manifest shape drifts and downstream deploy/promotion logic breaks unexpectedly."""
    manifest_path = tmp_path / "model_version_manifest.json"
    monkeypatch.setattr(model_logreg, "MODEL_MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(model_logreg, "DATA_DIR", tmp_path)

    expected = _valid_manifest_payload()
    model_logreg.save_model_manifest(expected)

    observed = model_logreg.load_model_manifest()
    assert observed is not None
    assert set(observed.keys()) == {"active_model", "active_metrics", "history"}
    assert isinstance(observed["history"], list)
    assert observed["history"]
    latest = observed["history"][-1]
    for field in (
        "version",
        "artifact",
        "metrics",
        "source_metrics",
        "label_source_counts",
        "dataset_size",
        "promotion_decision",
        "decision_reason",
    ):
        assert field in latest
