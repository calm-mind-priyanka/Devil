#!/bin/sh
set -e
cd "$(dirname "$0")"
pip3 install -U -r requirements.txt
echo "Starting Jisshu filter bot...."
exec python3 bot.py
