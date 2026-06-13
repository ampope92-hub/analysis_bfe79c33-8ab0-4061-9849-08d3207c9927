#!/bin/bash

TASK="_flask_test_summarization_game_bfe79c33-8ab0-4061-9849-08d3207c9927"
PROJECT_ID="bfe79c33-8ab0-4061-9849-08d3207c9927"
TEMPLATE="default"
TASK_PATH="$(cd "$(dirname "$0")" && pwd)"
SUBMIT="$TASK_PATH/../submit.sh"
CONFIG="$TASK_PATH/.snorkel_config"

case "$1" in
  oracle|test)
    # One command, this terminal: applies solution/solve.sh then runs tests/test.sh
    # in the container and reports reward/pass — no interactive env, no second terminal.
    stb harbor run -a oracle -p "$TASK_PATH" -o "$TASK_PATH/jobs"
    JOB="$(ls -dt "$TASK_PATH"/jobs/*/ 2>/dev/null | head -1)"
    REWARD="$(cat "$JOB"*/verifier/reward.txt 2>/dev/null | head -1)"
    TESTS="$(grep -hE '={3,}.*(passed|failed|error)' "$JOB"*/verifier/test-stdout.txt 2>/dev/null | tail -1 | sed 's/=//g; s/^ *//; s/ *$//')"
    echo ""
    echo "──────────────── ORACLE RESULT ────────────────"
    if [ "$REWARD" = "1" ]; then
      echo "  ✅ PASSED   reward=1"
    else
      echo "  ❌ FAILED   reward=${REWARD:-<none>}"
    fi
    [ -n "$TESTS" ] && echo "  tests: $TESTS"
    echo "  job:   ${JOB%/}"
    echo "────────────────────────────────────────────────"
    ;;
  trials)
    echo "Running 5x GPT trials..."
    for i in $(seq 1 5); do
      echo "  GPT trial $i/5"
      stb harbor run -m @openai/gpt-5.2 -p "$TASK_PATH"
    done
    echo "Running 5x Claude Opus trials..."
    for i in $(seq 1 5); do
      echo "  Claude trial $i/5"
      stb harbor run -m @anthropic/claude-opus-4-6 -p "$TASK_PATH"
    done
    ;;
  submit)
    # Create on first run, then auto-update via .snorkel_config on later runs.
    "$SUBMIT" "$TASK_PATH" "$PROJECT_ID" --time 180
    ;;
  update)
    # Update only — never create a duplicate (errors if no submission id is known).
    "$SUBMIT" "$TASK_PATH" "$PROJECT_ID" --no-create --time 180
    ;;
  feedback)
    # Show the reviewer's rubric / revision notes for this task's submission.
    if [ -f "$CONFIG" ]; then
      SID="$(grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' "$CONFIG" | head -n1)"
      [ -n "$SID" ] && stb submissions feedback "$SID" || echo "No submission id in $CONFIG yet."
    else
      echo "No .snorkel_config yet — submit first with ./terminus.sh submit"
    fi
    ;;
  *)
    echo "Usage: ./terminus.sh <command>"
    echo "Commands: oracle | test | trials | submit | update | feedback"
    exit 1
    ;;
esac
