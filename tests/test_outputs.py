import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Static / structural checks
# ---------------------------------------------------------------------------

def test_api_file_exists():
    """Flask API source file exists at api/app.py."""
    assert Path("/app/api/app.py").exists()


def test_api_uses_flask():
    """api/app.py imports Flask."""
    content = Path("/app/api/app.py").read_text()
    assert "Flask" in content or "flask" in content


def test_api_has_analyze_endpoint():
    """api/app.py defines a POST /analyze route."""
    content = Path("/app/api/app.py").read_text()
    assert "/analyze" in content


def test_api_has_evaluate_endpoint():
    """api/app.py defines a POST /evaluate route."""
    content = Path("/app/api/app.py").read_text()
    assert "/evaluate" in content


def test_game_script_exists():
    """game.py exists in /app."""
    assert Path("/app/game.py").exists()


def test_game_script_is_executable():
    """game.py has the executable bit set."""
    assert os.access("/app/game.py", os.X_OK), "game.py is not executable"


def test_game_script_accepts_document_argument():
    """game.py uses argparse or sys.argv to accept a document path."""
    content = Path("/app/game.py").read_text()
    assert "argparse" in content or "sys.argv" in content


def test_game_script_calls_api():
    """game.py makes HTTP requests to the API."""
    content = Path("/app/game.py").read_text()
    assert "requests" in content or "urllib" in content


def test_requirements_file_exists():
    """requirements.txt exists."""
    assert Path("/app/requirements.txt").exists()


def test_requirements_has_flask():
    """requirements.txt lists flask."""
    content = Path("/app/requirements.txt").read_text().lower()
    assert "flask" in content


def test_requirements_has_requests():
    """requirements.txt lists requests."""
    content = Path("/app/requirements.txt").read_text().lower()
    assert "requests" in content


def test_large_document_exists():
    """documents/ contains at least one .txt file with 37 500+ words (~50k tokens)."""
    docs_dir = Path("/app/documents")
    assert docs_dir.exists(), "documents/ directory does not exist"
    txt_files = list(docs_dir.glob("*.txt"))
    assert txt_files, "No .txt files found in /app/documents/"
    max_words = max(len(f.read_text(errors="replace").split()) for f in txt_files)
    assert max_words >= 37_500, (
        f"Largest document has {max_words:,} words; need >= 37,500 (~50k tokens)"
    )


# ---------------------------------------------------------------------------
# API functional tests — one shared server instance for the whole module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def api_server():
    """Start api/app.py, yield the process, terminate after tests."""
    import requests as req

    proc = subprocess.Popen(
        [sys.executable, "/app/api/app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Poll until Flask is accepting connections (up to 10 s)
    for _ in range(20):
        try:
            req.get("http://localhost:5000/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        # Even without /health, give Flask one more second then continue
        time.sleep(1)

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_analyze_returns_200(api_server):
    """POST /analyze returns HTTP 200."""
    import requests as req
    r = req.post(
        "http://localhost:5000/analyze",
        json={"text": "The quick brown fox jumps over the lazy dog. " * 100},
        timeout=15,
    )
    assert r.status_code == 200


def test_analyze_returns_word_count(api_server):
    """POST /analyze response includes a positive word_count integer."""
    import requests as req
    r = req.post(
        "http://localhost:5000/analyze",
        json={"text": "hello world testing " * 200},
        timeout=15,
    )
    data = r.json()
    assert "word_count" in data, f"word_count missing from response: {data}"
    assert isinstance(data["word_count"], int)
    assert data["word_count"] > 0


def test_analyze_returns_key_terms(api_server):
    """POST /analyze response includes a non-empty key_terms list."""
    import requests as req
    r = req.post(
        "http://localhost:5000/analyze",
        json={"text": "The elephant is a large mammal that roams the savanna. " * 100},
        timeout=15,
    )
    data = r.json()
    assert "key_terms" in data, f"key_terms missing from response: {data}"
    assert isinstance(data["key_terms"], list)
    assert len(data["key_terms"]) > 0


def test_analyze_returns_estimated_tokens(api_server):
    """POST /analyze response includes estimated_tokens."""
    import requests as req
    r = req.post(
        "http://localhost:5000/analyze",
        json={"text": "word " * 1000},
        timeout=15,
    )
    data = r.json()
    assert "estimated_tokens" in data, f"estimated_tokens missing: {data}"
    assert data["estimated_tokens"] > 0


def test_evaluate_returns_200(api_server):
    """POST /evaluate returns HTTP 200."""
    import requests as req
    r = req.post(
        "http://localhost:5000/evaluate",
        json={
            "original": "The history of computing involves many important figures. " * 100,
            "summary": "Computing history involves many important figures.",
        },
        timeout=15,
    )
    assert r.status_code == 200


def test_evaluate_returns_score_in_range(api_server):
    """POST /evaluate response includes a score between 0 and 100."""
    import requests as req
    r = req.post(
        "http://localhost:5000/evaluate",
        json={
            "original": "Dogs are loyal animals that make wonderful pets for families. " * 100,
            "summary": "Dogs are loyal animals and great pets.",
        },
        timeout=15,
    )
    data = r.json()
    assert "score" in data, f"score missing from response: {data}"
    assert 0 <= data["score"] <= 100


def test_evaluate_returns_feedback_string(api_server):
    """POST /evaluate response includes a non-empty feedback string."""
    import requests as req
    r = req.post(
        "http://localhost:5000/evaluate",
        json={
            "original": "Python is a high-level programming language. " * 100,
            "summary": "Python is a programming language.",
        },
        timeout=15,
    )
    data = r.json()
    assert "feedback" in data, f"feedback missing from response: {data}"
    assert isinstance(data["feedback"], str)
    assert len(data["feedback"].strip()) > 0


def test_evaluate_good_summary_outscores_poor(api_server):
    """A summary covering key terms scores higher than one that does not."""
    import requests as req

    original = (
        "The Python programming language was created by Guido van Rossum. "
        "Python emphasizes readability and simplicity. "
        "It supports object-oriented and functional programming paradigms. "
    ) * 100

    good = (
        "Python was created by Guido van Rossum and emphasizes readability "
        "and simplicity, supporting object-oriented and functional paradigms."
    )
    poor = "A programming language exists."

    good_score = req.post(
        "http://localhost:5000/evaluate",
        json={"original": original, "summary": good},
        timeout=15,
    ).json()["score"]

    poor_score = req.post(
        "http://localhost:5000/evaluate",
        json={"original": original, "summary": poor},
        timeout=15,
    ).json()["score"]

    assert good_score > poor_score, (
        f"Good summary ({good_score}) should outscore poor summary ({poor_score})"
    )
