import model_logreg


def test_rejects_candidate_when_elevated_recall_drops_past_threshold():
    """Real-world failure: poisoned writes lower elevated recall and silently replace safer incumbent."""
    incumbent = {
        "accuracy": 0.78,
        "elevated_recall": 0.80,
    }
    candidate = {
        "accuracy": 0.79,
        "elevated_recall": 0.69,
    }

    promote, reason = model_logreg.should_promote_model(candidate, incumbent)

    assert not promote
    assert reason == "elevated_recall_regression"


def test_rejects_candidate_when_accuracy_drops_past_threshold():
    """Real-world failure: poisoned candidate degrades overall holdout accuracy but still gets deployed."""
    incumbent = {
        "accuracy": 0.81,
        "elevated_recall": 0.72,
    }
    candidate = {
        "accuracy": 0.75,
        "elevated_recall": 0.71,
    }

    promote, reason = model_logreg.should_promote_model(candidate, incumbent)

    assert not promote
    assert reason == "accuracy_regression"


def test_promotes_candidate_when_no_significant_regression():
    """Real-world success path: safer candidate with stable metrics is allowed to become active model."""
    incumbent = {
        "accuracy": 0.77,
        "elevated_recall": 0.70,
    }
    candidate = {
        "accuracy": 0.78,
        "elevated_recall": 0.69,
    }

    promote, reason = model_logreg.should_promote_model(candidate, incumbent)

    assert promote
    assert reason == "passed"
