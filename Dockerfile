FROM python:3.10-slim

# System packages required by the bot + image/OCR processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-eng \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# App directory
WORKDIR /app

# Copy requirements first for better Docker caching
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

# Copy the complete bot
COPY . /app

# Make start script executable
RUN chmod +x /app/start.sh

# IMPORTANT: verify that the real OCR engine exists
RUN tesseract --version

# Start bot
CMD ["bash", "/app/start.sh"]
