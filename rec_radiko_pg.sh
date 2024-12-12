#!/bin/sh

LOCKFILE="/tmp/rec_radiko_pg.lock"
LOCKPID=$(cat $LOCKFILE 2>/dev/null)

cd `dirname $0`

# ロックファイルが存在し、かつプロセスが動作中の場合
if [ -e $LOCKFILE ] && kill -0 $LOCKPID 2>/dev/null; then
  echo "Script is already running with PID $LOCKPID."
  exit 1
fi

# 現在のプロセスIDをロックファイルに記録
echo $$ > $LOCKFILE

trap 'rm -f $LOCKFILE; exit $?' INT TERM EXIT

echo "Script is running..."
.venv/bin/python rec_radiko_pg.py

rm -f $LOCKFILE
trap - INT TERM EXIT

echo "Script finished."
