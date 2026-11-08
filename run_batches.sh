#!/bin/zsh
# Runs tailor-resumes.md several times in a row, each in a fresh headless AI session (5 jobs per session),
# so context never piles up. Stops early when a session logs no new jobs (list finished, or something broke).
# Usage: ./run_batches.sh [number_of_batches] [--codex]   (default 4 batches = 20 jobs, with Claude Code)
cd "$(dirname "$0")"
MAX=4
TOOL=claude
for arg in "$@"; do
  case "$arg" in
    --codex) TOOL=codex ;;
    <->) MAX=$arg ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done
command -v $TOOL >/dev/null || { echo "$TOOL is not installed or not on PATH."; exit 1; }
mkdir -p logs

NOTE='Headless run: nobody can answer questions, so never stop to ask.'
PROMPT="$(cat tailor-resumes.md)

$NOTE"

fmt() { printf '%02d:%02d' $(($1 / 60)) $(($1 % 60)); }
run_start=$SECONDS
pid=""
# Ctrl-C also stops the running AI session
trap '[ -n "$pid" ] && kill $pid 2>/dev/null; printf "\n"; exit 130' INT TERM

for i in $(seq 1 $MAX); do
  before=$(wc -l < applications.csv 2>/dev/null || echo 0)
  day_dir="logs/$(date +%Y-%m-%d)"   # one folder per day
  mkdir -p "$day_dir"
  log="$day_dir/batch_$(date +%H%M%S).md"
  echo "Batch $i/$MAX ($TOOL) -> $log"

  if [[ $TOOL == claude ]]; then
    claude -p "$PROMPT" \
      --permission-mode dontAsk \
      --allowedTools Read Edit Write WebFetch Agent \
        "Bash(resumes/render.sh:*)" "Bash(python3 fetch_job.py:*)" "Bash(head:*)" "Bash(tail:*)" "Bash(grep:*)" \
        "Bash(sed -n:*)" "Bash(cp:*)" "Bash(ls:*)" "Bash(wc:*)" \
      < /dev/null > "$log" 2>&1 &
  else
    # Codex: may write files in this folder only, with network on (to fetch job pages). Prompt comes from stdin.
    print -r -- "$PROMPT" | codex exec --sandbox workspace-write \
      -c 'sandbox_workspace_write.network_access=true' -c 'approval_policy="never"' - \
      > "$log" 2>&1 &
  fi
  pid=$!

  # Live timer on the bottom line while the session runs
  batch_start=$SECONDS
  while kill -0 $pid 2>/dev/null; do
    printf '\r\033[K⏱  Batch %d/%d running: %s  (total %s)' \
      $i $MAX "$(fmt $((SECONDS - batch_start)))" "$(fmt $((SECONDS - run_start)))"
    sleep 1
  done
  wait $pid
  printf '\r\033[K'
  echo "Batch $i finished in $(fmt $((SECONDS - batch_start))) (report: $log)"
  after=$(wc -l < applications.csv 2>/dev/null || echo 0)
  if [ "$after" -le "$before" ]; then
    echo "No new jobs logged; stopping. Check the report above for the reason."
    break
  fi
done
echo "All done in $(fmt $((SECONDS - run_start)))"
