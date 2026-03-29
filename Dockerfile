# Use a Python base image
FROM python:3.10-slim

# Install system dependencies (Only Redis needed now)
RUN apt-get update && apt-get install -y \
    redis-server \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything
COPY . .

# Ensure start.sh is executable
RUN chmod +x start.sh

# Expose port (HF Spaces and Render use 7860 here)
EXPOSE 7860

CMD ["./start.sh"]
