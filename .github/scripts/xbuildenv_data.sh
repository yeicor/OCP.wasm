#!/usr/bin/env sh

set -ex

GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/stderr}"

# Grab the wanted xbuildenv version from requirements-ci.txt
xbuildenv_version="$(grep -oP 'pyodide-xbuildenv==\K[0-9.]+' requirements.txt)"
if [ -z "$xbuildenv_version" ]; then
  echo -e "xbuildenv version not found in requirements-ci.txt:\n$(cat requirements.txt)"
  exit 1
fi
echo "xbuildenv_version=$xbuildenv_version" >>"$GITHUB_OUTPUT"

# Grab the related pyodide version from the main repo
xbuildenv_json="$(curl -s -q "https://raw.githubusercontent.com/pyodide/pyodide/refs/heads/main/pyodide-cross-build-environments.json" | jq -c --arg ver "$xbuildenv_version" '.releases[$ver]')"
if [ -z "$xbuildenv_json" ]; then
  echo "Failed to get xbuildenv JSON for version $xbuildenv_version"
  exit 1
fi
echo "Got xbuildenv JSON: $xbuildenv_json"

# Extract the Python version
python_version=$(echo "$xbuildenv_json" | jq -r '.python_version')
if [ -z "$python_version" ]; then
  echo "Python version not found in xbuildenv JSON"
  exit 1
fi
echo "python_version=$python_version" >>"$GITHUB_OUTPUT"
