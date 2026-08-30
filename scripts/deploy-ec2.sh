#!/bin/bash
set -euo pipefail

echo "RedBlue EC2 Deploy"
echo "=================="

cd /home/ec2-user/RedBlue 2>/dev/null || cd /home/ubuntu/RedBlue 2>/dev/null || {
  echo "RedBlue repo not found under ~/RedBlue"
  exit 1
}

echo "Pulling master..."
git fetch origin
git checkout master
git pull origin master

if [[ ! -f .env ]]; then
  echo "Missing .env — copy from .env.example and set secrets first"
  exit 1
fi

# Docker Compose DB must use service hostname "postgres"
if grep -qE '^DB_URL=.*@(localhost|127\.0\.0\.1)' .env; then
  echo "WARNING: DB_URL points at localhost. Inside containers use @postgres"
fi

echo "Rebuilding containers..."
docker compose down
docker compose build --no-cache frontend
docker compose up -d --build

echo "Waiting for health..."
for i in $(seq 1 60); do
  if curl -sf http://localhost:8000/health >/dev/null && curl -sf http://localhost:3000 >/dev/null; then
    echo "Backend + frontend healthy"
    break
  fi
  sleep 3
done

echo ""
echo "Deploy complete"
echo "  UI:   http://$(curl -s ifconfig.me 2>/dev/null || echo YOUR_EC2_IP):3000/mission-control"
echo "  API:  http://localhost:8000/docs"
echo "=================="
