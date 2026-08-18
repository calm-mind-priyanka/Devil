if [ -z $UPSTREAM_REPO ]
then
  echo "Cloning main Repository"
  git clone https://github.com/JisshuTG/Jisshu-filter-bot /Jisshu-filter-bot
else
  echo "Cloning Custom Repo from $UPSTREAM_REPO "
  git clone $UPSTREAM_REPO /Jisshu-filter-bot
fi
cd /Jisshu-filter-bot
pip3 install -U -r requirements.txt
echo "Starting Jisshu filter bot...."
python3 bot.py
