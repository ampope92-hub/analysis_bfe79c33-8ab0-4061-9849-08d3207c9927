import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

_FLASK_LOG = "/tmp/flask_server.log"

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


def test_game_script_accepts_document_argument(api_server):
    """game.py uses argparse or sys.argv to accept a document path."""
    docs = list(Path("/app/documents").glob("*.txt"))
    assert docs, "No .txt files found in /app/documents/"
    doc = docs[0]
    proc = subprocess.run(
        [sys.executable, "/app/game.py", str(doc)],
        input="This is my summary.\n", capture_output=True, text=True,
        timeout=30
    )
    assert proc.returncode == 0, f"game.py exited {proc.returncode}\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    out = proc.stdout.lower()
    # Word count stat must be shown as a large number (document has 37 500+ words)
    assert "word" in out, f"Expected word count stats in game output:\n{proc.stdout}"
    large_nums = [int(n.replace(",", "")) for n in re.findall(r'\d[\d,]*', out) if int(n.replace(",", "")) >= 10_000]
    assert large_nums, f"Expected a word count >= 10,000 displayed (doc is 37 500+ words):\n{proc.stdout}"
    # Numeric score from /evaluate must appear
    assert "score" in out, f"Expected evaluation score in game output:\n{proc.stdout}"
    scores = re.findall(r'score[:\s]+(\d+(?:\.\d+)?)', out)
    assert scores, f"No numeric score found in game output:\n{proc.stdout}"
    assert 0 <= float(scores[0]) <= 100, f"Score {scores[0]} out of range"
    # Feedback text from /evaluate must appear (not just the word "feedback")
    feedback_match = re.search(r'feedback[:\s]+(.{10,})', out)
    assert feedback_match, f"Expected feedback text from /evaluate in output:\n{proc.stdout}"


def test_game_script_calls_api_at_runtime(api_server):
    """game.py calls /analyze and /evaluate on the Flask server at runtime."""
    docs = list(Path("/app/documents").glob("*.txt"))
    assert docs, "No .txt files found in /app/documents/"
    proc = subprocess.run(
        [sys.executable, "/app/game.py", str(docs[0])],
        input="This is my summary.\n", capture_output=True, text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"game.py exited {proc.returncode}\nstderr: {proc.stderr}"
    logs = Path(_FLASK_LOG).read_text()
    assert "/analyze" in logs, f"No /analyze call found in Flask logs:\n{logs[-500:]}"
    assert "/evaluate" in logs, f"No /evaluate call found in Flask logs:\n{logs[-500:]}"


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
    """Start api/app.py, log output to file, yield the process."""
    import requests as req

    log = open(_FLASK_LOG, "w")
    proc = subprocess.Popen(
        [sys.executable, "/app/api/app.py"],
        stdout=log,
        stderr=log,
    )
    # Poll until Flask is accepting connections (up to 15 s)
    for _ in range(30):
        try:
            req.get("http://localhost:5000/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.terminate()
        log.close()
        pytest.fail("Flask API did not start within 15 seconds — check that api/app.py exists and runs correctly")

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()


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
    # Input is "hello world testing " * 200 = 600 words
    assert 580 <= data["word_count"] <= 620, (
        f"Expected ~600 words, got {data['word_count']}"
    )


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
    assert len(data["key_terms"]) >= 2
    terms_lower = [t.lower() for t in data["key_terms"]]
    assert any("elephant" in t for t in terms_lower), (
        f"Expected 'elephant' in key_terms for elephant text: {terms_lower}"
    )

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
    # "word " * 1000 = 1000 words ≈ 1300 tokens; accept a wide band
    assert data["estimated_tokens"] >= 800, (
        f"estimated_tokens too low for 1000-word input: {data['estimated_tokens']}"
    )
    assert data["estimated_tokens"] <= 2000, (
        f"estimated_tokens too high for 1000-word input: {data['estimated_tokens']}"
    )


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

    assert good_score > poor_score + 10, (
        f"Good summary ({good_score:.1f}) should outscore poor summary ({poor_score:.1f}) by >10 points"
    )


def test_evaluate_feedback_differs_by_score(api_server):
    """Feedback must reflect the score, not be a single canned string."""
    import requests as req

    original = "Climate change involves shifting global temperatures and weather patterns. " * 100

    good = req.post(
        "http://localhost:5000/evaluate",
        json={
            "original": original,
            "summary": "Climate change involves shifting global temperatures and weather patterns.",
        },
        timeout=15,
    ).json()
    poor = req.post(
        "http://localhost:5000/evaluate",
        json={"original": original, "summary": "x"},
        timeout=15,
    ).json()

    assert good["feedback"] != poor["feedback"], (
        f"Feedback must vary with score; got identical string: {good['feedback']!r}"
    )


def test_evaluate_coverage_beats_length(api_server):
    """Topic coverage must drive the score — same-length off-topic summary must score much lower."""
    import requests as req

    original = (
        "The Python programming language was created by Guido van Rossum. "
        "Python emphasizes readability and simplicity with clear syntax. "
        "It supports object-oriented, functional, and procedural paradigms. "
    ) * 80

    # Similar word counts (~22 words each), but only on_topic covers key terms
    on_topic = (
        "Python was created by Guido van Rossum and emphasizes readability "
        "and simplicity, supporting object-oriented and functional paradigms."
    )
    off_topic = (
        "The weather outside is pleasant today and colourful birds are singing "
        "cheerfully in the tall green trees near the quiet river bank."
    )

    on_score = req.post(
        "http://localhost:5000/evaluate",
        json={"original": original, "summary": on_topic},
        timeout=15,
    ).json()["score"]

    off_score = req.post(
        "http://localhost:5000/evaluate",
        json={"original": original, "summary": off_topic},
        timeout=15,
    ).json()["score"]

    assert on_score > off_score + 20, (
        f"On-topic summary ({on_score:.1f}) should outscore same-length off-topic summary "
        f"({off_score:.1f}) by >20 points. Scorer must weight topic coverage, not just length."
    )
