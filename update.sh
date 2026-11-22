#!/bin/bash
# Pull the latest code. Deploy it only if it compiles and the test suite passes; otherwise keep the running version.
set -u
cd /opt/telegram-bots || exit 1
git fetch -q origin main || exit 0
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] && exit 0
rm -rf /tmp/tb-check && git worktree add -f -q /tmp/tb-check origin/main || exit 1
if (cd /tmp/tb-check && python3 -m py_compile bot.py && python3 test_bot.py >/dev/null); then
  git reset -q --hard origin/main
  cp telegram-bot@.service telegram-bots-update.service telegram-bots-update.timer /etc/systemd/system/
  systemctl daemon-reload
  systemctl restart 'telegram-bot@*'
  echo "deployed $(git rev-parse --short HEAD)"
else
  echo "rejected $(git rev-parse --short origin/main): tests failed"
fi
git worktree remove -f /tmp/tb-check
