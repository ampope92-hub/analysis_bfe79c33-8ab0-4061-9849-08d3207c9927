Hey, I'm trying to build a little text-analysis game and I need someone to put the pieces together.

The idea: there's a Flask API that does two things — analyzes a long text document (returns word count, sentence count, key terms, etc.) and evaluates a user-written summary against the original (returns a 0–100 score based on how well the summary covers the key topics and has a sensible length). Then there's a separate game script that a player runs from the command line. It loads a big document, shows the player some stats about it, lets them read it and type in a summary, calls the API to score the summary, and prints their results.

The "big document" part is important — we want the documents to be at least 50,000 tokens so there's actually a challenge to summarizing them. No cheating with tiny files.

Here's the structure I'm picturing:

- `api/app.py` — the Flask app, running on port 5000, with a `POST /analyze` endpoint that takes `{"text": "..."}` and a `POST /evaluate` endpoint that takes `{"original": "...", "summary": "..."}`
- `game.py` — the CLI game script, takes a document path as its first argument, calls the API, runs the interactive session
- `documents/` — a folder with at least one `.txt` file that's large enough to use (50k+ tokens)
- `requirements.txt` — with `flask` and `requests` listed

The `/analyze` response should include at least `word_count`, `key_terms` (a list), and `estimated_tokens`. The `/evaluate` response needs at least `score` (0–100 float) and `feedback` (a string explaining how well they did).

Make sure `game.py` is executable. The API and game should work together when you start Flask in one terminal and run the game script in another. One thing — run the Flask app with `debug=False` (or just don't pass `debug=True`). Debug mode spawns a reloader process that can cause weird timeout issues when the server is started in the background.

Important: the summary must be the only thing `game.py` reads from stdin. Don't add menus, mode selections, or any other prompts that consume input before the summary. The game should load the document, show the stats, then read the summary directly from stdin — nothing else. This lets it work non-interactively (e.g. `echo "my summary" | python game.py doc.txt`).
