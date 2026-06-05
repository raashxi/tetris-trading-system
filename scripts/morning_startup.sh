#!/bin/bash
set -e

echo "========================================="
echo "TRADING BOT MORNING STARTUP CHECK"
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="

cd "$(dirname "$0")/.."

# Check for STOP file
if [ -f "STOP" ]; then
    echo "❌ STOP file found. Halting startup."
    echo "Remove STOP file to proceed: rm STOP"
    exit 1
fi

# Check Docker is running
if ! docker ps > /dev/null 2>&1; then
    echo "❌ Docker is not running. Start Docker Desktop first."
    exit 1
fi

echo "✅ Docker is running"

# Check .env file exists and is a file
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    exit 1
fi

echo "✅ .env file found"

# Create necessary directories
mkdir -p logs models data

echo ""
echo "========================================="
echo "✅ All checks passed!"
echo "Run: docker-compose up -d"
echo "========================================="
