#!/bin/bash
#
# DLNA Server Stress Test
# Runs 10 parallel playmedia tests for 120 seconds to test server under load.
#

set -e

HOST="${1:-localhost}"
PORT="${2:-8200}"
DURATION=120
NUM_WORKERS=10

echo "=== DLNA Server Stress Test ==="
echo "Target: $HOST:$PORT"
echo "Duration: ${DURATION}s"
echo "Workers: $NUM_WORKERS"
echo ""

# Track PIDs and create a temp dir for status files
PIDS=()
TMPDIR=$(mktemp -d)
trap 'kill "${PIDS[@]}" 2>/dev/null; rm -rf "$TMPDIR"' EXIT

START_TIME=$(date +%s)
END_TIME=$((START_TIME + DURATION))

# Worker function
worker() {
    local id=$1
    local status_file="$TMPDIR/worker_$id"
    local count=0

    while [ "$(date +%s)" -lt "$END_TIME" ]; do
        if ! uv run dlna-tester "$HOST" "$PORT" -p > /dev/null 2>&1; then
            echo "FAILED" > "$status_file"
            echo "[Worker $id] FAILED after $count successful runs"
            exit 1
        fi
        count=$((count + 1))
    done

    echo "$count" > "$status_file"
    echo "[Worker $id] Completed $count runs"
}

echo "Starting $NUM_WORKERS workers..."
echo ""

# Start workers
for i in $(seq 1 $NUM_WORKERS); do
    worker "$i" &
    PIDS+=($!)
done

# Wait for all workers and check for failures
FAILED=0
for pid in "${PIDS[@]}"; do
    if ! wait "$pid"; then
        FAILED=1
    fi
done

echo ""

if [ "$FAILED" -eq 1 ]; then
    echo "=== STRESS TEST FAILED ==="
    echo "One or more workers encountered an error."
    exit 1
fi

# Sum up total runs
TOTAL=0
for i in $(seq 1 $NUM_WORKERS); do
    if [ -f "$TMPDIR/worker_$i" ]; then
        COUNT=$(cat "$TMPDIR/worker_$i")
        if [ "$COUNT" != "FAILED" ]; then
            TOTAL=$((TOTAL + COUNT))
        fi
    fi
done

echo "=== STRESS TEST PASSED ==="
echo "Total playback simulations: $TOTAL"
echo "Duration: ${DURATION}s"
echo "Average: $(echo "scale=2; $TOTAL / $DURATION" | bc) runs/sec"
