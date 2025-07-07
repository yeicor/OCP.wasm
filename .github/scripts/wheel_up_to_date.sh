#!/usr/bin/env sh

set -ex

GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/stderr}"

last_wheel_date=$(stat --format %Y ${{ matrix.package }}/wheelhouse/*.whl | sort -n | tail -n 1)
echo "Last wheel date: $(date -d @$last_wheel_date)"

last_sources_date=$(git log -1 --format=%cd --date=unix -- ${{ matrix.package }})
echo "Last sources date: $(date -d @$last_sources_date)"
git log -1 -- ${{ matrix.package }} # Show the last commit message modifying sources for debugging

# TODO: More robust checks like the version of xbuildenv (which could mean more pyodide versions), etc.
#       As a workaround, I disabled the inter-branch caching for now
if [ "$last_wheel_date" -gt "$last_sources_date" ]; then
  echo "Skipping build, cached artifact should be up to date! (${last_wheel_date} > ${last_sources_date})"
  echo "skip_build=true" >>"$GITHUB_OUTPUT"
fi
