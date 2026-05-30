Hey, I'm trying to build a little text-analysis game and I need someone to put the pieces together.

The idea: there's a Flask API that does two things — analyzes a long text document (returns word count, sentence count, key terms, etc.) and evaluates a user-written summary against the original (returns a 0–100 score based on how well the summary covers the key topics and has a sensible length). Then there's a separate game script that a player runs from the command line. It loads a big document, shows the player some stats about it, lets them read it and type in a summary, calls the API to score the summary, and prints their results.

The "big document" part is important — the documents need to be at least 50,000 tokens so there's actually a challenge to summarizing them. No cheating with tiny files.

Here's the structure I'm picturing:

- `api/app.py` — the Flask app, running on port 5000, with a `POST /analyze` endpoint that takes `{"text": "..."}` and a `POST /evaluate` endpoint that takes `{"original": "...", "summary": "..."}`
- `game.py` — the CLI game script, takes a document path as its first argument, calls the API, runs the interactive session
- `documents/` — a folder with at least one `.txt` file that's large enough to use (50k+ tokens)
- `requirements.txt` — with `flask` and `requests` listed

The `/analyze` response should include at least `word_count`, `sentence_count`, `key_terms` (a list), and `estimated_tokens`. The `/evaluate` response needs at least `score` (0–100 float) and `feedback` (a string explaining how well they did).

One more endpoint: `POST /compare` for head-to-head scoring. Takes `{"original": "...", "summary_a": "...", "summary_b": "..."}` and returns `{"winner": "a" | "b" | "tie", "score_a": float, "score_b": float, "margin": float}`. `winner` must be exactly one of those three lowercase strings, `margin` is the absolute difference between the two scores (never negative), and identical summaries should produce a tie.

All three endpoints should return a 400 error if any required field is missing from the request body — don't silently default to empty strings or zero values. Also treat a field that is present but contains only whitespace the same as a missing field — return 400. The 400 response body must be valid JSON (not an HTML error page) — Flask's built-in `abort(400)` returns HTML, so return a JSON response explicitly.

`word_count` must count only alphabetic tokens — digits, punctuation-only tokens, and mixed alphanumeric strings like "abc123" don't count as words.

The `/compare` endpoint must be symmetric: swapping `summary_a` and `summary_b` must produce the same scores (just swapped) and the same `margin`.

Make sure `game.py` is executable. The API and game should work together when you start Flask in one terminal and run the game script in another. One thing — run the Flask app with `debug=False` (or just don't pass `debug=True`). Debug mode spawns a reloader process that can cause weird timeout issues when the server is started in the background.

Important: the summary must be the only thing `game.py` reads from stdin. Don't add menus, mode selections, or any other prompts that consume input before the summary. The game should load the document, show the stats, then read the summary directly from stdin — nothing else. This lets it work non-interactively (e.g., `echo "my summary" | python game.py doc.txt`).
