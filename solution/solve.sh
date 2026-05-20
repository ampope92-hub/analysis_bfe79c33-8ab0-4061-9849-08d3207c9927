#!/usr/bin/env bash
set -euo pipefail

# ── directory structure ─────────────────────────────────────────────────────
mkdir -p api documents

# ── requirements.txt ────────────────────────────────────────────────────────
cat > requirements.txt << 'EOF'
flask>=3.0.0
requests>=2.31.0
EOF

pip install --quiet -r requirements.txt 2>/dev/null || true

# ── Flask API ────────────────────────────────────────────────────────────────
cat > api/app.py << 'PYEOF'
from flask import Flask, request, jsonify
import re
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

def _words(text):
    return re.findall(r'\b[a-zA-Z]+\b', text.lower())

def _key_terms(text, n=30):
    filtered = [w for w in _words(text) if w not in _STOP and len(w) > 3]
    return [w for w, _ in Counter(filtered).most_common(n)]


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json(silent=True) or {}
    text = data.get('text', '')
    if not text:
        return jsonify({'error': 'Missing text field'}), 400

    words = _words(text)
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    estimated_tokens = max(1, len(text) // 4)

    return jsonify({
        'word_count': len(words),
        'sentence_count': len(sentences),
        'paragraph_count': len(paragraphs),
        'character_count': len(text),
        'estimated_tokens': estimated_tokens,
        'key_terms': _key_terms(text),
    })


@app.route('/evaluate', methods=['POST'])
def evaluate():
    data = request.get_json(silent=True) or {}
    original = data.get('original', '')
    summary  = data.get('summary', '')
    if not original or not summary:
        return jsonify({'error': 'Missing original or summary field'}), 400

    orig_terms  = set(_key_terms(original, 30))
    summ_words  = set(_words(summary))
    covered     = sum(1 for t in orig_terms if t in summ_words)
    coverage    = (covered / len(orig_terms) * 100) if orig_terms else 0.0

    orig_len = len(_words(original))
    summ_len = len(_words(summary))
    ratio    = summ_len / orig_len if orig_len else 0.0

    if 0.05 <= ratio <= 0.20:
        length_score = 100.0
    elif ratio < 0.05:
        length_score = (ratio / 0.05) * 100.0
    else:
        length_score = max(0.0, 100.0 - ((ratio - 0.20) / 0.80) * 100.0)

    total = round(coverage * 0.7 + length_score * 0.3, 1)

    if total >= 80:
        feedback = "Excellent! Your summary captures the key themes and is well-proportioned."
    elif total >= 60:
        feedback = "Good work. You covered most of the important content."
    elif coverage < 40:
        feedback = "Your summary misses many key topics — try to mention the main subjects more explicitly."
    elif ratio > 0.25:
        feedback = "Your summary is too long. Be more concise — aim for 5–20% of the original length."
    elif ratio < 0.03:
        feedback = "Your summary is too brief. Include more of the key ideas."
    else:
        feedback = "Keep working on identifying and including the most important concepts."

    return jsonify({
        'score': total,
        'coverage_score': round(coverage, 1),
        'length_score': round(length_score, 1),
        'key_terms_covered': covered,
        'total_key_terms': len(orig_terms),
        'summary_word_count': summ_len,
        'original_word_count': orig_len,
        'compression_ratio': round(ratio * 100, 1),
        'feedback': feedback,
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
PYEOF

# ── CLI game ─────────────────────────────────────────────────────────────────
cat > game.py << 'PYEOF'
#!/usr/bin/env python3
"""Interactive Text Analysis Game — test your summarization skills."""

import argparse
import sys
import requests

_API = "http://localhost:5000"
_W   = 64


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
        print("Start the server first:  python api/app.py")
        sys.exit(1)
    return text, r.json()


def _collect_summary():
    print("Read the document, then type your summary below.")
    print("Press Enter twice when finished.")
    print("-" * _W)
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        lines.append(line)
        if len(lines) >= 2 and lines[-1] == "" and lines[-2] == "":
            break
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


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
    if score >= 80:
        print("  *** EXCELLENT WORK! ***")
    elif score >= 60:
        print("  Good job — try again to beat your score!")
    else:
        print("  Keep practising — summarization is a skill!")
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

    summary = _collect_summary()
    if not summary.strip():
        print("No summary entered. Exiting.")
        sys.exit(1)

    print("\nEvaluating…")
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

# ── large document (~40 000 words, no internet required) ─────────────────────
python3 << 'PYEOF'
import random, os, textwrap

random.seed(2024)

SENTENCES = [
    # Technology & Computing
    "The development of the transistor at Bell Laboratories in 1947 by Shockley, Bardeen, and Brattain marked a pivotal moment in human technological achievement.",
    "Alan Turing's theoretical concept of a universal computing machine, described in his landmark 1936 paper, laid the intellectual foundation for all modern digital computers.",
    "The invention of the integrated circuit by Jack Kilby and Robert Noyce in 1958 and 1959 respectively allowed thousands of transistors to be fabricated on a single chip.",
    "Moore's Law, articulated by Gordon Moore in 1965, observed that the number of transistors on a chip doubles roughly every two years, driving decades of exponential progress.",
    "The development of the internet grew from ARPANET, a US Defense Department project intended to create a resilient communication network capable of surviving nuclear attack.",
    "Tim Berners-Lee invented the World Wide Web in 1989 while working at CERN, proposing a hypertext system to allow physicists to share information across different computers.",
    "Open-source software movements democratized programming by allowing developers worldwide to inspect, modify, and redistribute source code freely.",
    "Machine learning algorithms enable computers to improve their performance on tasks through experience, without being explicitly programmed for each scenario.",
    "The Python programming language, created by Guido van Rossum and first released in 1991, became one of the most popular languages due to its readable syntax and vast ecosystem.",
    "Cloud computing transformed software delivery by allowing applications and data to be hosted on remote servers and accessed via the internet from any device.",
    "Cryptography underpins digital security, using mathematical algorithms to encrypt data so that only authorized parties can read it.",
    "Artificial neural networks, inspired by the structure of biological brains, learn by adjusting the weights of connections between simulated neurons during training.",
    "Version control systems such as Git allow teams of developers to collaborate on code, tracking every change and enabling rollbacks to previous states.",
    "The microprocessor, placing an entire CPU on a single chip, enabled the personal computer revolution of the 1970s and 1980s.",
    "Relational databases store data in structured tables and allow complex queries through the Structured Query Language, forming the backbone of modern enterprise applications.",
    "Containerization technologies like Docker package applications and their dependencies into isolated environments, simplifying deployment across different infrastructure.",
    "The agile software development methodology emphasizes iterative delivery, cross-functional collaboration, and responding to change over following a fixed plan.",
    "Graph neural networks extend deep learning to graph-structured data, enabling breakthroughs in drug discovery, social network analysis, and recommendation systems.",
    "Natural language processing allows computers to understand, interpret, and generate human language, powering assistants, translation services, and text analysis tools.",
    "Quantum computing leverages quantum mechanical phenomena such as superposition and entanglement to perform certain calculations exponentially faster than classical machines.",

    # Science & Nature
    "Photosynthesis is the biochemical process by which plants, algae, and cyanobacteria convert sunlight, water, and carbon dioxide into glucose and oxygen.",
    "The theory of evolution by natural selection, proposed independently by Darwin and Wallace, explains how species change over time through differential reproductive success.",
    "DNA, the molecule that carries genetic information, consists of two complementary strands wound into a double helix first described by Watson and Crick in 1953.",
    "Climate change refers to long-term shifts in global temperatures and weather patterns, significantly accelerated by human emissions of greenhouse gases since industrialization.",
    "Plate tectonics describes the movement of the rigid lithospheric plates that make up Earth's surface, explaining earthquakes, volcanoes, and the formation of mountain ranges.",
    "The electromagnetic spectrum encompasses all wavelengths of electromagnetic radiation, from radio waves and microwaves through visible light to ultraviolet, X-ray, and gamma radiation.",
    "Ecology is the scientific study of how organisms interact with each other and with their physical environment, encompassing populations, communities, and ecosystems.",
    "The periodic table organizes all known chemical elements by atomic number and electron configuration, revealing recurring patterns in their properties.",
    "Black holes form when massive stars collapse at the end of their lives, creating regions of spacetime where gravity is so strong that nothing, not even light, can escape.",
    "CRISPR-Cas9 gene editing technology, derived from a bacterial immune system, allows scientists to make precise cuts in DNA, opening new possibilities for medicine and agriculture.",
    "The ocean covers more than seventy percent of Earth's surface and plays a critical role in regulating climate, absorbing carbon dioxide and distributing heat globally.",
    "Vaccines train the immune system to recognize and combat pathogens by introducing harmless antigens, preventing disease without causing infection.",
    "Neuroplasticity refers to the brain's ability to reorganize itself by forming new neural connections throughout life, enabling learning and recovery from injury.",
    "Cosmological inflation theory proposes that the universe underwent an extremely rapid exponential expansion in the first fractions of a second after the Big Bang.",
    "Antibiotic resistance emerges when bacteria evolve mechanisms to survive drugs designed to kill them, representing a growing global public health threat.",
    "The nitrogen cycle describes how nitrogen moves through the atmosphere, soil, water, and living organisms, driven by bacteria that fix, nitrify, and denitrify the element.",
    "Supernovae occur when massive stars exhaust their nuclear fuel and collapse catastrophically, releasing more energy in seconds than the sun will emit over its entire lifetime.",
    "Epigenetics studies heritable changes in gene expression that do not involve alterations to the underlying DNA sequence, influenced by environment and behavior.",
    "Renewable energy sources such as solar, wind, and hydroelectric power generate electricity without depleting finite resources or emitting significant greenhouse gases.",
    "The microbiome, the community of trillions of microorganisms living in and on the human body, plays crucial roles in digestion, immunity, and even mental health.",

    # History & Society
    "The Agricultural Revolution, beginning around ten thousand years ago, transformed human societies from nomadic hunter-gatherers into settled farming communities.",
    "The printing press, invented by Johannes Gutenberg around 1440, revolutionized the spread of information and played a central role in the Protestant Reformation and Scientific Revolution.",
    "The Industrial Revolution, originating in Britain in the late eighteenth century, transformed manufacturing through mechanization, urbanization, and new energy sources.",
    "The Renaissance was a cultural and intellectual movement in Europe spanning the fourteenth to seventeenth centuries, marked by renewed interest in classical art, literature, and learning.",
    "Colonialism reshaped the political, cultural, and economic landscapes of vast regions of Asia, Africa, and the Americas, with consequences that continue to shape the modern world.",
    "The French Revolution of 1789 dismantled the ancien régime and introduced principles of liberty, equality, and popular sovereignty that influenced political movements worldwide.",
    "The Cold War, a prolonged geopolitical tension between the United States and the Soviet Union, shaped global politics, economics, and culture from 1947 until the Soviet collapse in 1991.",
    "Globalization has accelerated the exchange of goods, services, capital, people, and ideas across national borders, creating both opportunities and significant challenges.",
    "The Universal Declaration of Human Rights, adopted by the United Nations in 1948, articulated fundamental rights and freedoms to which all people are entitled.",
    "Urbanization has been one of the dominant demographic trends of the past two centuries, with more than half of the global population now living in cities.",
    "The abolition of slavery across the nineteenth century represented a major moral achievement, though its legacy of racism and inequality persists in many societies.",
    "The Green Revolution of the mid-twentieth century dramatically increased agricultural yields in developing countries through improved crop varieties, irrigation, and fertilizers.",
    "Democracy, as a system of government, rests on principles of popular sovereignty, majority rule, minority rights, and the peaceful transfer of power.",
    "The Silk Road network of trade routes connected China, Central Asia, the Middle East, and Europe for over a millennium, facilitating the exchange of goods and ideas.",
    "Pandemics throughout history, from the Black Death to the 1918 influenza, have reshaped populations, economies, and social institutions in profound ways.",
    "The scientific method, developed during the seventeenth century, relies on observation, hypothesis formation, experimentation, and peer review to build reliable knowledge.",
    "Economic inequality has grown in many countries over recent decades, raising debates about taxation, social mobility, education access, and the role of government.",
    "Decolonization movements in the twentieth century led to the independence of dozens of nations in Africa, Asia, and the Caribbean from European colonial rule.",
    "The welfare state emerged in many industrialized nations during the twentieth century, providing citizens with social insurance against unemployment, illness, and old age.",
    "International trade agreements have lowered tariffs and reduced barriers between nations, integrating economies but also exposing workers and industries to global competition.",

    # Philosophy & Ideas
    "Epistemology, the branch of philosophy concerned with the nature and scope of knowledge, asks fundamental questions about what we can know and how we can justify our beliefs.",
    "Utilitarianism holds that the morally correct action is the one that produces the greatest good for the greatest number of people.",
    "Existentialism emphasizes individual freedom, choice, and responsibility, asserting that humans create their own meaning in an inherently meaningless universe.",
    "The philosophy of science investigates the methods, foundations, and implications of science, examining how theories are constructed, tested, and revised.",
    "Ethics explores questions of right and wrong, virtue and vice, and the principles that should govern individual and collective behavior.",
    "Phenomenology, founded by Edmund Husserl, studies the structures of conscious experience and aims to describe phenomena as they appear to the observing subject.",
    "Political philosophy examines questions of justice, authority, liberty, and rights, exploring how societies should be organized and governed.",
    "Rationalism holds that reason is the primary source of knowledge, while empiricism maintains that knowledge comes fundamentally from sensory experience.",
    "The philosophy of mind investigates the nature of consciousness, mental states, and the relationship between mind and body.",
    "Critical theory analyzes social structures and ideologies, seeking to expose and challenge forms of domination and open possibilities for emancipation.",
]

HEADINGS = [
    "Chapter One: The Foundations of Modern Knowledge",
    "Chapter Two: Technological Revolutions and Their Consequences",
    "Chapter Three: The Natural World and Scientific Discovery",
    "Chapter Four: Human History and Civilization",
    "Chapter Five: Ideas, Philosophy, and Society",
    "Chapter Six: Interconnections and Emerging Challenges",
    "Chapter Seven: Looking Forward — Synthesis and Reflection",
]

os.makedirs("documents", exist_ok=True)

target = 40_000
written = 0
chapter_idx = 0
para_in_chapter = 0
chapter_threshold = 55  # paragraphs per chapter

with open("documents/document.txt", "w", encoding="utf-8") as fh:
    fh.write(HEADINGS[0] + "\n\n")
    while written < target:
        n = random.randint(5, 9)
        chosen = random.choices(SENTENCES, k=n)
        paragraph = " ".join(chosen)
        fh.write(paragraph + "\n\n")
        written += len(paragraph.split())
        para_in_chapter += 1

        if para_in_chapter >= chapter_threshold:
            para_in_chapter = 0
            chapter_idx = min(chapter_idx + 1, len(HEADINGS) - 1)
            fh.write(HEADINGS[chapter_idx] + "\n\n")

print(f"Generated document.txt with ~{written:,} words (~{written*4//3:,} estimated tokens)")
PYEOF
