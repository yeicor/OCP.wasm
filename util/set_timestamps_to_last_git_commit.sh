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

# Try to get the last Git commit timestamp
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  last_commit_ts=$(git log -1 --pretty=format:'%ad' --date=format:%Y%m%d%H%M.%S 2>/dev/null)
else
  last_commit_ts=""
fi

# Validate timestamp format
if echo "$last_commit_ts" | grep -Eq '^[0-9]{12}(\.[0-9]{2})?$'; then
  ts="$last_commit_ts"
else
  echo "Warning: using fallback timestamp (this may reuse old caches on updates!):"
  ts="200001010000.00" # TODO: Use some version file to extract a more appropriate timestamp
fi

# Apply timestamp to all files
find . -type f -exec touch -t "$ts" {} +

echo "-- All file timestamps set to: $ts"
