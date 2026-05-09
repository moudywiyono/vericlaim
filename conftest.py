import os
from pathlib import Path

import pytest


# Keep tests from accidentally loading a real .env that has VERICLAIM_ALLOW_GOLD_EVAL set
@pytest.fixture(autouse=True)
def block_gold_eval_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERICLAIM_ALLOW_GOLD_EVAL", raising=False)


@pytest.fixture
def sample_claim_dir(tmp_path: Path) -> Path:
    """Minimal valid claim directory for unit tests."""
    manifest = {
        "claim_id": "test-001",
        "claim_type": None,
        "images": [],
        "pdfs": [],
        "audio": [],
        "form_data": {
            "claimant_name": "Jane Doe",
            "incident_date": "2026-04-01",
            "description": "Minor rear-end collision at low speed.",
        },
    }
    import json

    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).parent


# Silence HuggingFace progress bars during tests
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
