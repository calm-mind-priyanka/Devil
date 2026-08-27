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
pip3 install -U -r requirements.txt
echo "Starting Jisshu filter bot...."
python3 bot.py
