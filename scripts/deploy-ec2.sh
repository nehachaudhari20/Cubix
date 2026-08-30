#!/bin/bash
set -e

echo "🚀 RedBlue EC2 Deploy"
echo "====================="

# Pull latest code
echo "📦 Pulling latest code..."
cd /home/ubuntu/RedBlue 2>/dev/null || cd /home/ec2-user/RedBlue 2>/dev/null || { echo "❌ RedBlue repo not found"; exit 1; }
git pull origin feat/mastercard-ui-v1

# Backend — build and start with docker-compose
echo "🐳 Building and starting backend containers..."
docker compose down
docker compose up -d --build

# Wait for backend to be healthy
echo "⏳ Waiting for backend to be healthy..."
for i in $(seq 1 30); do
  if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Backend is healthy on :8000"
    break
  fi
  sleep 2
done

# Frontend — install deps, build, start
echo "🏗️  Building frontend..."
cd frontend
npm install
npm run build

# Start frontend on port 3000
echo "🌐 Starting frontend on :3000..."
pkill -f "next start" 2>/dev/null || true
nohup npx next start -p 3000 > /tmp/frontend.log 2>&1 &

sleep 3
if curl -s http://localhost:3000 > /dev/null 2>&1; then
  echo "✅ Frontend is live on :3000"
else
  echo "⚠️  Frontend may still be starting — check http://localhost:3000"
fi

echo ""
echo "====================="
echo "✅ Deploy complete!"
echo "   Backend:  http://localhost:8000"
echo "   Frontend: http://localhost:3000"
echo "   Docs:     http://localhost:8000/docs"
echo "====================="
