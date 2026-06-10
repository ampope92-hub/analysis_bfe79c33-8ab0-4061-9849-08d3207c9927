"""Text-analysis API. Work in progress — known to be flaky, several things are wrong."""
from flask import Flask, request, jsonify, abort
from collections import Counter

app = Flask(__name__)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json(silent=True) or {}
    text = data.get('text', '')
    if 'text' not in data:
        abort(400)

    words = text.split()
    sentences = text.split('.')

    return jsonify({
        'word_count': len(words),
        'unique_word_count': len(set(words)),
        'sentence_count': len(sentences),
        'estimated_tokens': len(text) // 4,
        'key_terms': [w for w, _ in Counter(words).most_common(10)],
    })


@app.route('/evaluate', methods=['POST'])
def evaluate():
    data = request.get_json(silent=True) or {}
    original = data.get('original', '')
    summary = data.get('summary', '')
    if not original or not summary:
        abort(400)

    ratio = len(summary.split()) / max(1, len(original.split()))
    score = min(100.0, ratio * 500)

    return jsonify({
        'score': score,
        'feedback': 'Thanks for your summary.',
        'coverage_score': 0,
        'length_score': score,
        'key_terms_covered': 0,
        'total_key_terms': 0,
        'compression_ratio': round(ratio * 100, 1),
    })


@app.route('/compare', methods=['POST'])
def compare():
    data = request.get_json(silent=True) or {}
    a = data.get('summary_a', '')
    b = data.get('summary_b', '')

    if a == b:
        return jsonify({'winner': 'tie', 'score_a': 0, 'score_b': 0, 'margin': 0})

    sa = len(a.split())
    sb = len(b.split())
    winner = 'a' if sa > sb else 'b'
    return jsonify({'winner': winner, 'score_a': sa, 'score_b': sb, 'margin': abs(sa - sb)})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
