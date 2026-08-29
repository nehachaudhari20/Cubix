#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "Starting backend..."
.venv/bin/python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --log-level warning &
PID=$!
trap "kill $PID 2>/dev/null" EXIT

# Wait for server
for i in $(seq 1 20); do
  if curl -s --max-time 1 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "Server UP in ${i}s"
    break
  fi
  sleep 1
done

echo ""
echo "=== HEALTH ==="
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
echo ""

echo "=== PLATFORM STATUS ==="
curl -s http://127.0.0.1:8000/api/platform/status | python3 -m json.tool
echo ""

echo "=== BUFFER ==="
curl -s http://127.0.0.1:8000/api/platform/buffer | python3 -m json.tool
echo ""

echo "=== BUFFER RECENT ==="
curl -s "http://127.0.0.1:8000/api/platform/buffer/recent?limit=2" | python3 -m json.tool
echo ""

echo "=== RUNS ==="
curl -s "http://127.0.0.1:8000/api/platform/runs?limit=3" | python3 -m json.tool
echo ""

echo "=== LOOP RUNNING ==="
curl -s http://127.0.0.1:8000/api/platform/loop/running | python3 -m json.tool
echo ""

echo "=== SCHEDULER ==="
curl -s http://127.0.0.1:8000/api/platform/scheduler | python3 -m json.tool
echo ""

echo "=== KB STATS ==="
curl -s http://127.0.0.1:8000/api/kb/stats | python3 -m json.tool
echo ""

echo "=== KB FAMILIES ==="
curl -s "http://127.0.0.1:8000/api/kb/families?limit=2" | python3 -m json.tool
echo ""

echo "=== KB SIGNALS ==="
curl -s "http://127.0.0.1:8000/api/kb/signals?limit=2" | python3 -m json.tool
echo ""

echo "=== KB STAGES ==="
curl -s http://127.0.0.1:8000/api/kb/stages | python3 -m json.tool
echo ""

echo "=== MISSING: /evaluation ==="
curl -s http://127.0.0.1:8000/api/platform/runs/test-id/evaluation | python3 -m json.tool 2>/dev/null || curl -s http://127.0.0.1:8000/api/platform/runs/test-id/evaluation
echo ""

echo "=== MISSING: /failure-analysis ==="
curl -s http://127.0.0.1:8000/api/platform/runs/test-id/failure-analysis | python3 -m json.tool 2>/dev/null || curl -s http://127.0.0.1:8000/api/platform/runs/test-id/failure-analysis
echo ""
