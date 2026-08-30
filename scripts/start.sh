#!/bin/bash
# Start both backend and frontend servers
# Usage: bash scripts/start.sh

cd "$(dirname "$0")/.."

echo "Starting PostgreSQL Docker container..."
docker start pdt-postgres 2>/dev/null || docker-compose up -d postgres
sleep 2

echo "Starting backend on port 8000..."
.venv/bin/python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 &
BPID=$!

echo "Starting frontend on port 3000..."
cd frontend && pnpm dev --port 3000 &
FPID=$!

echo ""
echo "✅ Servers started!"
echo "   Backend:  http://localhost:8000 (PID: $BPID)"
echo "   Frontend: http://localhost:3000 (PID: $FPID)"
echo "   Postgres: localhost:5432 (Docker: pdt-postgres)"
echo ""
echo "Press Ctrl+C to stop both servers."

wait
