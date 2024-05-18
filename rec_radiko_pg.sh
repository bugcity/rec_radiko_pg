#!/bin/sh

LOCKFILE="/tmp/rec_radiko_pg.lock"

cd `dirname $0`

if [ -e $LOCKFILE ]; then
  echo "Script is already running."
  exit 1
fi

touch $LOCKFILE

trap 'rm -f $LOCKFILE; exit $?' INT TERM EXIT

echo "Script is running..."
.venv/bin/python rec_radiko_pg.py

rm -f $LOCKFILE
trap - INT TERM EXIT

echo "Script finished."
