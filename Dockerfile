FROM python:3.10-slim

# Install system packages required by the bot and OCR
RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-eng \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the complete project
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    if [ -f requirements.txt ]; then \
        pip install --no-cache-dir -r requirements.txt; \
    fi

# Make startup script executable if present
RUN if [ -f start.sh ]; then chmod +x start.sh; fi

# Start the bot
CMD ["bash", "start.sh"]
