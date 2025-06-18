#!/usr/bin/env sh

if [ -z "$1" ]; then
  echo "Usage: $0 <directory>"
  exit 1
fi

if [ ! -z "$_FORCE_OLD_SOURCES" ]; then
  echo "-- Setting old timestamps for all files in $1"
else
  echo "-- Skipping setting old timestamps for files in $1"
  exit 0
fi

find "$1" -type f -exec touch -t 200001010000.00 {} +
