#!/bin/bash
# Start Redis
redis-server --daemonize yes

# Start Ollama
ollama serve &

# Wait for Ollama to be ready
echo "Waiting for Ollama..."
sleep 5

# Pull Mistral (Required for the agent)
echo "Pulling Mistral model into the container..."
ollama pull mistral

# Start the Agent
echo "Starting FastAPI Backend on Port 7860..."
uvicorn server.main:app --host 0.0.0.0 --port 7860
