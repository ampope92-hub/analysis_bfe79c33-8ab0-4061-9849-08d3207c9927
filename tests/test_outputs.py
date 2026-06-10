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


def test_analyze_returns_sentence_count(api_server):
    """POST /analyze response includes a positive sentence_count integer."""
    import requests as req
    r = req.post(
        "http://localhost:5000/analyze",
        json={"text": "The cat sat on the mat. The dog barked loudly. Birds flew away. " * 50},
        timeout=15,
    )
    data = r.json()
    assert "sentence_count" in data, f"sentence_count missing from response: {data}"
    assert isinstance(data["sentence_count"], int), (
        f"sentence_count must be an int, got {type(data['sentence_count'])}"
    )
    # Input is 3 sentences * 50 = 150 sentences
    assert 130 <= data["sentence_count"] <= 170, (
        f"Expected ~150 sentences, got {data['sentence_count']}"
    )


def test_analyze_handles_no_sentence_punctuation(api_server):
    """POST /analyze handles text with no sentence-ending punctuation without crashing."""
    import requests as req
    r = req.post(
        "http://localhost:5000/analyze",
        json={"text": "hello world"},
        timeout=15,
    )
    assert r.status_code == 200, (
        f"Expected 200 for unpunctuated text, got {r.status_code}: {r.text[:200]}"
    )
    data = r.json()
    assert data.get("word_count", 0) >= 1
    assert isinstance(data.get("sentence_count"), int)
    assert data.get("sentence_count", -1) >= 0


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


def test_analyze_rejects_missing_fields(api_server):
    """POST /analyze returns 4xx with a JSON body when the required 'text' field is missing."""
    import requests as req
    r = req.post(
        "http://localhost:5000/analyze",
        json={},
        timeout=15,
    )
    assert 400 <= r.status_code < 500, (
        f"Expected 4xx for missing 'text' field; got {r.status_code}: {r.text[:200]}"
    )
    try:
        body = r.json()
    except Exception:
        raise AssertionError(
            f"400 response body must be valid JSON, not HTML. Got: {r.text[:200]}"
        )
    assert isinstance(body, dict), f"400 response must be a JSON object, got: {body}"


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


def test_compare_returns_winner(api_server):
    """A clearly better summary wins the comparison and margin is non-negative."""
    import requests as req
    original = "Python was created by Guido van Rossum and emphasizes readability. " * 80
    r = req.post(
        "http://localhost:5000/compare",
        json={
            "original": original,
            "summary_a": "Python was created by Guido van Rossum and emphasizes readability.",
            "summary_b": "x",
        },
        timeout=15,
    )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
    data = r.json()
    assert data.get("winner") == "a", f"Expected winner 'a', got {data.get('winner')!r}"
    assert data["score_a"] > data["score_b"]
    assert abs(data["margin"] - abs(data["score_a"] - data["score_b"])) < 0.01, (
        f"margin must equal abs(score_a - score_b); got margin={data['margin']}, "
        f"score_a={data['score_a']}, score_b={data['score_b']}"
    )


def test_compare_b_wins(api_server):
    """summary_b winning sets winner='b' and score_b > score_a."""
    import requests as req
    original = "Python was created by Guido van Rossum and emphasizes readability. " * 80
    r = req.post(
        "http://localhost:5000/compare",
        json={
            "original": original,
            "summary_a": "x",
            "summary_b": "Python was created by Guido van Rossum and emphasizes readability.",
        },
        timeout=15,
    )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
    data = r.json()
    assert data.get("winner") == "b", f"Expected winner 'b', got {data.get('winner')!r}"
    assert data["score_b"] > data["score_a"]
    assert abs(data["margin"] - abs(data["score_a"] - data["score_b"])) < 0.01, (
        f"margin must equal abs(score_a - score_b); got margin={data['margin']}, "
        f"score_a={data['score_a']}, score_b={data['score_b']}"
    )


def test_compare_handles_ties(api_server):
    """Identical summaries must produce a tie."""
    import requests as req
    r = req.post(
        "http://localhost:5000/compare",
        json={
            "original": "The same text repeats here. " * 100,
            "summary_a": "A summary about repeating text.",
            "summary_b": "A summary about repeating text.",
        },
        timeout=15,
    ).json()
    assert r["winner"] == "tie", f"Identical summaries must tie; got {r['winner']!r}"


def test_compare_tie_is_score_based(api_server):
    """Tie detection must compare scores, not strings — summaries differing by trailing whitespace must tie."""
    import requests as req
    original = "Python was created by Guido van Rossum and emphasizes readability. " * 80
    summary = "Python was created by Guido van Rossum and emphasizes readability."
    r = req.post(
        "http://localhost:5000/compare",
        json={
            "original": original,
            "summary_a": summary,
            "summary_b": summary + " ",
        },
        timeout=15,
    ).json()
    assert r["winner"] == "tie", (
        f"Summaries differing only by trailing whitespace must tie; got winner={r['winner']!r}. "
        "Tie detection must compare scores, not strings."
    )


def test_compare_rejects_missing_fields(api_server):
    """POST /compare returns 4xx with a JSON body when summary_b is missing."""
    import requests as req
    r = req.post(
        "http://localhost:5000/compare",
        json={"original": "some text", "summary_a": "a"},
        timeout=15,
    )
    assert 400 <= r.status_code < 500, (
        f"Expected 4xx for missing summary_b; got {r.status_code}: {r.text[:200]}"
    )
    try:
        body = r.json()
    except Exception:
        raise AssertionError(
            f"400 response body must be valid JSON, not HTML. Got: {r.text[:200]}"
        )
    assert isinstance(body, dict), f"400 response must be a JSON object, got: {body}"


def test_evaluate_rejects_missing_fields(api_server):
    """POST /evaluate must return a 4xx JSON error when required fields are missing."""
    import requests as req
    r = req.post(
        "http://localhost:5000/evaluate",
        json={"original": "Some text without a summary field."},
        timeout=15,
    )
    assert 400 <= r.status_code < 500, (
        f"Expected 4xx for missing 'summary' field; got {r.status_code}: {r.text[:200]}"
    )
    try:
        body = r.json()
    except Exception:
        raise AssertionError(
            f"400 response body must be valid JSON, not HTML. Got: {r.text[:200]}"
        )
    assert isinstance(body, dict), f"400 response must be a JSON object, got: {body}"


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


def test_analyze_rejects_whitespace_only_text(api_server):
    """POST /analyze must return 400 when 'text' is present but contains only whitespace."""
    import requests as req
    r = req.post(
        "http://localhost:5000/analyze",
        json={"text": "   \t\n  "},
        timeout=15,
    )
    assert 400 <= r.status_code < 500, (
        f"Expected 4xx for whitespace-only 'text'; got {r.status_code}: {r.text[:200]}"
    )
    assert isinstance(r.json(), dict), "400 response must be a JSON object"


def test_evaluate_rejects_whitespace_only_fields(api_server):
    """POST /evaluate must return 400 when 'original' or 'summary' is present but whitespace-only."""
    import requests as req
    # whitespace-only summary
    r = req.post(
        "http://localhost:5000/evaluate",
        json={"original": "Some real original text here.", "summary": "   \t\n  "},
        timeout=15,
    )
    assert 400 <= r.status_code < 500, (
        f"Expected 4xx for whitespace-only 'summary'; got {r.status_code}: {r.text[:200]}"
    )
    try:
        body = r.json()
    except Exception:
        raise AssertionError(
            f"400 response body must be valid JSON, not HTML. Got: {r.text[:200]}"
        )
    assert isinstance(body, dict), f"400 response must be a JSON object, got: {body}"

    # whitespace-only original
    r2 = req.post(
        "http://localhost:5000/evaluate",
        json={"original": "\n  \t ", "summary": "A real summary."},
        timeout=15,
    )
    assert 400 <= r2.status_code < 500, (
        f"Expected 4xx for whitespace-only 'original'; got {r2.status_code}: {r2.text[:200]}"
    )
    try:
        body2 = r2.json()
    except Exception:
        raise AssertionError(
            f"400 response body must be valid JSON, not HTML. Got: {r2.text[:200]}"
        )
    assert isinstance(body2, dict), f"400 response must be a JSON object, got: {body2}"


def test_analyze_word_count_excludes_numbers(api_server):
    """word_count must count only alphabetic tokens — digits and mixed tokens don't count."""
    import requests as req
    r = req.post(
        "http://localhost:5000/analyze",
        json={"text": "hello world 123 456 abc123 test"},
        timeout=15,
    )
    data = r.json()
    # Only "hello", "world", "test" are purely alphabetic (abc123 is mixed, 123/456 are digits)
    assert data["word_count"] == 3, (
        f"Expected word_count=3 (alphabetic only), got {data['word_count']}. "
        f"Numbers and mixed tokens must not be counted."
    )


def test_analyze_word_count_counts_contractions_and_hyphens(api_server):
    """Contractions and hyphenated words count once; numeric/mixed tokens are rejected."""
    import requests as req
    r = req.post(
        "http://localhost:5000/analyze",
        json={"text": "don't well-known cats can't co-operate 123 well123"},
        timeout=15,
    )
    data = r.json()
    # don't, well-known, cats, can't, co-operate = 5 words;
    # "123" (digits) and "well123" (mixed) must NOT count.
    assert data["word_count"] == 5, (
        f"Expected word_count=5 (contractions/hyphenated count once, numeric/mixed "
        f"tokens excluded), got {data['word_count']}"
    )


def test_analyze_sentence_count_ignores_abbreviations_and_decimals(api_server):
    """sentence_count must not split on decimals (3.5) or title abbreviations (Dr./Mr.)."""
    import requests as req
    r = req.post(
        "http://localhost:5000/analyze",
        json={"text": "Dr. Smith measured 3.5 degrees today. Mr. Jones agreed. The team left."},
        timeout=15,
    )
    data = r.json()
    # Three real sentences; a naive split on '.' would report many more.
    assert data["sentence_count"] == 3, (
        f"Expected sentence_count=3 — periods in 'Dr.', 'Mr.', and '3.5' must not end "
        f"a sentence. Got {data['sentence_count']}."
    )


def test_analyze_key_terms_excludes_stopwords(api_server):
    """key_terms must filter common stopwords, even frequent multi-letter ones."""
    import requests as req
    r = req.post(
        "http://localhost:5000/analyze",
        json={"text": "there there there would would about elephant elephant savanna savanna mammoth " * 20},
        timeout=15,
    )
    data = r.json()
    terms = [t.lower() for t in data["key_terms"]]
    for stop in ("there", "would", "about"):
        assert stop not in terms, (
            f"Stopword {stop!r} must not appear in key_terms; got {terms}"
        )
    assert any("elephant" in t for t in terms), (
        f"Expected real topic words like 'elephant' in key_terms; got {terms}"
    )


def test_analyze_returns_unique_word_count(api_server):
    """POST /analyze must include unique_word_count — distinct alphabetic tokens, case-insensitive."""
    import requests as req
    # Mixed case on purpose: Hello/hello/HELLO and World/WORLD must collapse
    # case-insensitively → {hello, world, test} = 3 unique words. A case-SENSITIVE
    # implementation would report 6 here, so this input distinguishes the two.
    r = req.post(
        "http://localhost:5000/analyze",
        json={"text": "Hello hello HELLO World WORLD test"},
        timeout=15,
    )
    data = r.json()
    assert "unique_word_count" in data, (
        f"unique_word_count missing from /analyze response: {data}"
    )
    assert isinstance(data["unique_word_count"], int), (
        f"unique_word_count must be an int, got {type(data['unique_word_count'])}: {data['unique_word_count']}"
    )
    assert data["unique_word_count"] == 3, (
        f"Expected unique_word_count=3 (case-insensitive: hello/world/test), got "
        f"{data['unique_word_count']}. A case-sensitive count would wrongly return 6."
    )


def test_compare_rejects_whitespace_only_summary_fields(api_server):
    """POST /compare must return 400 when summary_a or summary_b is whitespace-only (same rule as /analyze)."""
    import requests as req
    r = req.post(
        "http://localhost:5000/compare",
        json={"original": "some text here", "summary_a": "   \t", "summary_b": "real summary"},
        timeout=15,
    )
    assert 400 <= r.status_code < 500, (
        f"Expected 4xx for whitespace-only summary_a; got {r.status_code}: {r.text[:200]}"
    )
    assert isinstance(r.json(), dict), "400 response must be a JSON object"

    r2 = req.post(
        "http://localhost:5000/compare",
        json={"original": "some text here", "summary_a": "real summary", "summary_b": "\n  \n"},
        timeout=15,
    )
    assert 400 <= r2.status_code < 500, (
        f"Expected 4xx for whitespace-only summary_b; got {r2.status_code}: {r2.text[:200]}"
    )
    assert isinstance(r2.json(), dict), "400 response must be a JSON object"


def test_game_shows_sentence_count(api_server):
    """game.py must display sentence count alongside the other document stats."""
    docs = list(Path("/app/documents").glob("*.txt"))
    assert docs, "No .txt files found in /app/documents/"
    doc = docs[0]
    proc = subprocess.run(
        [sys.executable, "/app/game.py", str(doc)],
        input="This is my summary.\n", capture_output=True, text=True,
        timeout=30,
    )
    assert proc.returncode == 0, f"game.py exited non-zero\nstderr: {proc.stderr}"
    out = proc.stdout.lower()
    assert "sentence" in out, (
        f"Expected sentence count in game.py output — game should show stats from /analyze "
        f"including sentence_count:\n{proc.stdout[:500]}"
    )


def test_compare_is_symmetric(api_server):
    """compare(a, b) and compare(b, a) must produce swapped-but-equal scores and the same margin."""
    import requests as req
    original = "Python was created by Guido van Rossum and emphasizes readability. " * 80
    summary_a = "Python was created by Guido van Rossum and emphasizes readability."
    summary_b = "A completely unrelated sentence about the weather and birds."

    ab = req.post(
        "http://localhost:5000/compare",
        json={"original": original, "summary_a": summary_a, "summary_b": summary_b},
        timeout=15,
    ).json()
    ba = req.post(
        "http://localhost:5000/compare",
        json={"original": original, "summary_a": summary_b, "summary_b": summary_a},
        timeout=15,
    ).json()

    assert abs(ab["score_a"] - ba["score_b"]) < 0.01, (
        f"score_a in (a,b) must equal score_b in (b,a): {ab['score_a']} vs {ba['score_b']}"
    )
    assert abs(ab["score_b"] - ba["score_a"]) < 0.01, (
        f"score_b in (a,b) must equal score_a in (b,a): {ab['score_b']} vs {ba['score_a']}"
    )
    assert abs(ab["margin"] - ba["margin"]) < 0.01, (
        f"margin must be the same regardless of order: {ab['margin']} vs {ba['margin']}"
    )
