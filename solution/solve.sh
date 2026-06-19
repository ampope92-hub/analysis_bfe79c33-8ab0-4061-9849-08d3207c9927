#!/usr/bin/env bash
set -euo pipefail

# The environment ships a buggy skeleton at /app (api/app.py, game.py, a large
# document, requirements.txt). The oracle fixes the code to meet the spec.
# The large document under /app/documents/ is provided by the image and is left
# untouched.

cd /app
mkdir -p api documents

# ── requirements.txt ────────────────────────────────────────────────────────
cat > requirements.txt << 'EOF'
flask==3.1.0
requests==2.32.3
EOF

# ── Flask API (corrected) ────────────────────────────────────────────────────
cat > api/app.py << 'PYEOF'
from flask import Flask, request, jsonify
import re
import string
from collections import Counter

app = Flask(__name__)

_STOP = {
    'the','a','an','and','or','but','in','on','at','to','for','of','with','by',
    'from','as','is','was','are','were','be','been','being','have','has','had',
    'do','does','did','will','would','could','should','may','might','must','can',
    'that','this','these','those','it','its','he','she','they','we','you','i',
    'not','no','so','if','then','than','when','where','who','which','what','how',
    'all','each','every','both','few','more','most','other','some','such','only',
    'own','same','also','very','just','into','up','out','about','after','before',
    'between','through','during','his','her','their','our','your','my','me',
    'him','them','us','any','there','here','now','too','one','two','three',
    'said','says','say','get','got','make','made','take','took','come','came',
    'went','go','see','seen','know','knew','think','thought','look','looked',
}

# Title abbreviations whose trailing period does not end a sentence.
_ABBREV = {'dr','mr','mrs','ms','prof','sr','jr','st','vs','rev','gen','sen','gov'}

# A word is alphabetic, optionally joined by internal apostrophes or hyphens
# (so "don't" and "well-known" are single words). Surrounding punctuation is
# stripped first; any token containing a digit is rejected entirely.
_WORD_RE = re.compile(r"[a-z]+(?:['’-][a-z]+)*")
_EDGE = string.punctuation + "…—–“”‘’"


def _words(text):
    out = []
    for raw in text.lower().split():
        tok = raw.strip(_EDGE)
        if tok and _WORD_RE.fullmatch(tok):
            out.append(tok)
    return out


def _sentence_count(text):
    # Protect decimals (3.5) and abbreviations (Dr.) from being read as enders.
    t = re.sub(r'(?<=\d)\.(?=\d)', '', text)
    t = re.sub(r'\b(' + '|'.join(_ABBREV) + r')\.', r'\1', t, flags=re.IGNORECASE)
    return len([s for s in re.split(r'[.!?]+', t) if s.strip()])


def _key_terms(text, n=30):
    filtered = [w for w in _words(text) if w not in _STOP and len(w) > 3]
    return [w for w, _ in Counter(filtered).most_common(n)]


def _score(original, summary):
    orig_terms = set(_key_terms(original, 30))
    summ_words = set(_words(summary))
    covered = sum(1 for t in orig_terms if t in summ_words)
    coverage = (covered / len(orig_terms) * 100) if orig_terms else 0.0

    orig_len = len(_words(original))
    summ_len = len(_words(summary))
    ratio = summ_len / orig_len if orig_len else 0.0

    if 0.05 <= ratio <= 0.20:
        length_score = 100.0
    elif ratio < 0.05:
        length_score = (ratio / 0.05) * 100.0
    else:
        length_score = max(0.0, 100.0 - ((ratio - 0.20) / 0.80) * 100.0)

    total = round(coverage * 0.7 + length_score * 0.3, 1)
    return total, coverage, length_score, covered, len(orig_terms), orig_len, summ_len, ratio


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json(silent=True) or {}
    text = data.get('text')
    if not isinstance(text, str) or not text.strip():
        return jsonify({'error': 'Missing or empty text field'}), 400

    words = _words(text)
    return jsonify({
        'word_count': len(words),
        'unique_word_count': len(set(words)),
        'sentence_count': _sentence_count(text),
        'character_count': len(text),
        'estimated_tokens': max(1, len(text) // 4),
        'key_terms': _key_terms(text),
    })


@app.route('/evaluate', methods=['POST'])
def evaluate():
    data = request.get_json(silent=True) or {}
    original = data.get('original')
    summary = data.get('summary')
    if (not isinstance(original, str) or not original.strip()
            or not isinstance(summary, str) or not summary.strip()):
        return jsonify({'error': 'Missing or empty original/summary field'}), 400

    total, coverage, length_score, covered, n_terms, orig_len, summ_len, ratio = _score(original, summary)

    if total >= 80:
        feedback = "Excellent! Your summary captures the key themes and is well-proportioned."
    elif total >= 60:
        feedback = "Good work. You covered most of the important content."
    elif coverage < 40:
        feedback = "Your summary misses many key topics — mention the main subjects more explicitly."
    elif ratio > 0.25:
        feedback = "Your summary is too long. Be more concise — aim for 5-20% of the original length."
    elif ratio < 0.03:
        feedback = "Your summary is too brief. Include more of the key ideas."
    else:
        feedback = "Keep working on identifying and including the most important concepts."

    return jsonify({
        'score': total,
        'feedback': feedback,
        'coverage_score': round(coverage, 1),
        'length_score': round(length_score, 1),
        'key_terms_covered': covered,
        'total_key_terms': n_terms,
        'summary_word_count': summ_len,
        'original_word_count': orig_len,
        'compression_ratio': round(ratio * 100, 1),
    })


@app.route('/compare', methods=['POST'])
def compare():
    data = request.get_json(silent=True) or {}
    original = data.get('original')
    summary_a = data.get('summary_a')
    summary_b = data.get('summary_b')
    if not isinstance(original, str) or not original.strip():
        return jsonify({'error': 'Missing or empty original field'}), 400
    if (not isinstance(summary_a, str) or not summary_a.strip()
            or not isinstance(summary_b, str) or not summary_b.strip()):
        return jsonify({'error': 'Missing or empty summary_a/summary_b field'}), 400

    score_a = _score(original, summary_a)[0]
    score_b = _score(original, summary_b)[0]
    margin = abs(score_a - score_b)
    if margin < 0.01:
        winner = 'tie'
    elif score_a > score_b:
        winner = 'a'
    else:
        winner = 'b'

    return jsonify({
        'winner': winner,
        'score_a': score_a,
        'score_b': score_b,
        'margin': round(margin, 2),
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
PYEOF

# ── CLI game (corrected) ──────────────────────────────────────────────────────
cat > game.py << 'PYEOF'
#!/usr/bin/env python3
"""Text Analysis Game — summarize a long document and get scored."""

import argparse
import sys
import requests

_API = "http://localhost:5000"
_W = 64


def _bar(char="="):
    print(char * _W)


def _header(title):
    _bar()
    print(f"  {title}")
    _bar()


def _analyze(path, api_url):
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    try:
        r = requests.post(f"{api_url}/analyze", json={"text": text}, timeout=60)
        r.raise_for_status()
    except requests.exceptions.ConnectionError:
        print(f"\nError: cannot connect to API at {api_url}")
        print("Start the server first:  python /app/api/app.py")
        sys.exit(1)
    return text, r.json()


def _show_info(info):
    print()
    print("Document stats:")
    print(f"  Words:            {info.get('word_count', 0):,}")
    print(f"  Sentences:        {info.get('sentence_count', 0):,}")
    print(f"  Estimated tokens: {info.get('estimated_tokens', 0):,}")
    terms = info.get("key_terms", [])[:10]
    if terms:
        print(f"  Key terms:        {', '.join(terms)}")
    print()


def _show_results(ev):
    print()
    _header("RESULTS")
    score = ev.get("score", 0)
    print(f"  Overall Score:      {score:.1f} / 100")
    print(f"  Coverage Score:     {ev.get('coverage_score', 0):.1f} / 100")
    print(f"  Length Score:       {ev.get('length_score', 0):.1f} / 100")
    print(f"  Key Terms Covered:  {ev.get('key_terms_covered', 0)} / {ev.get('total_key_terms', 0)}")
    print(f"  Compression:        {ev.get('compression_ratio', 0):.1f}%")
    print()
    print(f"  Feedback: {ev.get('feedback', '')}")
    _bar()


def main():
    parser = argparse.ArgumentParser(
        description="Text Analysis Game — summarize a long document and get scored."
    )
    parser.add_argument("document", help="Path to the document to summarize")
    parser.add_argument("--api-url", default=_API, help=f"Flask API URL (default: {_API})")
    args = parser.parse_args()

    _header("TEXT ANALYSIS GAME — Summarization Challenge")
    print()
    print(f"Loading: {args.document}")

    text, info = _analyze(args.document, args.api_url)
    _show_info(info)

    print("Read the document, then type your summary and press Ctrl-D:")
    print("-" * _W)
    summary = sys.stdin.read()
    if not summary.strip():
        print("No summary entered. Exiting.")
        sys.exit(1)

    print("\nEvaluating...")
    try:
        r = requests.post(
            f"{args.api_url}/evaluate",
            json={"original": text, "summary": summary},
            timeout=60,
        )
        r.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("Error: cannot connect to API.")
        sys.exit(1)

    _show_results(r.json())


if __name__ == "__main__":
    main()
PYEOF
chmod +x game.py
