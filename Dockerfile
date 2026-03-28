# Use a Python base image
FROM python:3.10-slim

# Install system dependencies (Redis and Ollama)
RUN apt-get update && apt-get install -y \
    redis-server \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -L https://ollama.com/install.sh | sh

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything
COPY . .

# Ensure start.sh is executable
RUN chmod +x start.sh

# HF Spaces uses port 7860
EXPOSE 7860

CMD ["./start.sh"]
