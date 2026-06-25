#!/bin/bash
# Real-time deployment script for UCD

TARGET_PORT=${1:-3000}
TARGET_ENV=${2:-production}

echo "================================"
echo "Starting deployment to: $TARGET_ENV"
echo "Target port: $TARGET_PORT"
echo "================================"

# Verify Node.js is installed
if ! command -v node &> /dev/null; then
    echo "Node.js not found. Installing Node.js..."
    sudo apt-get update -y
    sudo apt-get install -y nodejs npm
fi

# Go to deployment directory (where the script is running)
CDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$CDIR"
echo "Working directory: $CDIR"

# Install npm dependencies
echo "Installing dependencies..."
npm install --no-audit --no-fund

# Check if there is an active process running on the target port and kill it
echo "Cleaning up any process running on port $TARGET_PORT..."
PID=$(lsof -t -i:$TARGET_PORT)
if [ ! -z "$PID" ]; then
    echo "Found process $PID on port $TARGET_PORT, terminating it..."
    kill -9 $PID
else
    # Fallback to fuser if lsof is not present or returns empty
    sudo fuser -k $TARGET_PORT/tcp || true
fi

# Run the app in background with the correct port and environment variables
echo "Launching Node.js application in background..."
export PORT=$TARGET_PORT
export NODE_ENV=$TARGET_ENV
nohup node server.js > app.log 2>&1 &

# Wait a few seconds and check if it is running
sleep 3
if ps -ef | grep "node server.js" | grep -q "PORT=$TARGET_PORT"; then
    echo "Deployment SUCCESSFUL! Application running on port $TARGET_PORT"
else
    # Simple check on port status
    if ss -tln | grep -q ":$TARGET_PORT "; then
        echo "Deployment SUCCESSFUL! Port $TARGET_PORT is listening."
    else
        echo "Warning: Application may not have started properly. Check app.log."
        cat app.log | tail -n 20
    fi
fi

echo "================================"
