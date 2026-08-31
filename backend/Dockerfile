FROM python:3.11-slim

# Install system dependencies (build tools for compiling spacy/thinc if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the English language model for spaCy
RUN python -m spacy download en_core_web_sm

# Set PYTHONPATH to project root so 'backend.pipeline' imports work
ENV PYTHONPATH=/app
