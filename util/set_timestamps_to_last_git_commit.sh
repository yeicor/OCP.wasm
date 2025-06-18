#!/usr/bin/env sh

if [ -z "$1" ]; then
  echo "Usage: $0 <directory>"
  exit 1
fi

if [ -z "$_FORCE_OLD_SOURCES" ]; then
  echo "-- Skipping setting old timestamps for files in $1"
  exit 0
else
  echo "-- Setting last Git commit timestamp for all files in $1"
fi

# Change into the target directory
cd "$1" || exit 1

# Get last commit date in YYYYMMDDhhmm.ss format
last_commit_ts=$(git log -1 --pretty=format:'%ad' --date=format:%Y%m%d%H%M.%S 2>/dev/null)

# Validate format (should be 12 digits + optional .ss)
if ! echo "$last_commit_ts" | grep -Eq '^[0-9]{12}(\.[0-9]{2})?$'; then
  echo "Error: invalid timestamp format: $last_commit_ts"
  exit 1
fi

# Apply the timestamp to all files
find . -type f -exec touch -t "$last_commit_ts" {} +

echo "-- All file timestamps set to: $last_commit_ts"
