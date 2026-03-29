#!/bin/bash
# Start Redis
redis-server --daemonize yes

# Start the Agent
echo "Starting FastAPI Backend on Port 7860..."
uvicorn server.main:app --host 0.0.0.0 --port 7860
