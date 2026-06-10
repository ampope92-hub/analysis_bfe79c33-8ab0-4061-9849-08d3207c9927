#!/usr/bin/env python3
"""Summarization game CLI. Half-finished — doesn't quite work yet."""
import sys
import requests

API = "http://localhost:5000"


def main():
    if len(sys.argv) < 2:
        print("usage: game.py <document>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    info = requests.post(f"{API}/analyze", json={"text": text}).json()
    print("Document loaded.")
    print(f"Words: {info.get('word_count')}")

    mode = input("Choose mode (1=easy, 2=hard): ")
    print(f"Mode {mode} selected. Type your summary:")
    summary = input()

    ev = requests.post(f"{API}/evaluate", json={"original": text, "summary": summary}).json()
    print(f"Score: {ev.get('score')}")


main()
