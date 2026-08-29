#!/bin/bash
set -e
if [ -f bot.py ]; then
  echo "Using the current repository files"
elif [ -n "$UPSTREAM_REPO" ]; then
  echo "Cloning Custom Repo from $UPSTREAM_REPO"
  git clone "$UPSTREAM_REPO" /Jisshu-filter-bot
  cd /Jisshu-filter-bot
elif [ ! -f bot.py ]; then
  echo "Cloning main Repository"
  git clone https://github.com/JisshuTG/Jisshu-filter-bot /Jisshu-filter-bot
  cd /Jisshu-filter-bot
fi
if command -v tesseract >/dev/null 2>&1; then
  echo "Tesseract OCR: $(tesseract --version 2>&1 | head -n 1)"
else
  echo "ERROR: Tesseract OCR executable is missing"
  exit 1
fi
echo "Starting Jisshu filter bot...."
python3 bot.py
