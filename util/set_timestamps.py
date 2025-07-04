import os
import sys
import subprocess
import re
from pathlib import Path
from datetime import datetime

def usage():
    print(f"Usage: {sys.argv[0]} <directory>")
    sys.exit(1)

def get_last_commit_timestamp():
    if os.path.isdir('.git'):
        try:
            subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            result = subprocess.run(["git", "log", "-1", "--pretty=format:%ad", "--date=format-local:%Y%m%d%H%M.%S"],
                                    check=True, capture_output=True, text=True)
            timestamp = result.stdout.strip()
            if re.fullmatch(r"\d{12}(\.\d{2})?", timestamp):
                return timestamp
        except subprocess.CalledProcessError:
            pass
    print(f"Warning: Using fallback timestamp for {os.getcwd()}")
    return "200001010000.00"  # Fallback timestamp

def set_file_timestamps(target_dir, timestamp):
    for path in Path(target_dir).rglob('*'):
        if path.is_file():
            try:
                subprocess.run(["touch", "-t", timestamp, str(path)], check=True)
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to set timestamp for {path}: {e}")

def main():
    if len(sys.argv) != 2:
        usage()

    target_dir = sys.argv[1]
    if not os.path.isdir(target_dir):
        print(f"Error: '{target_dir}' is not a valid directory.")
        sys.exit(1)

    if os.environ.get("_FORCE_OLD_SOURCES") is None:
        print(f"-- Skipping setting old timestamps for files in {target_dir}")
        sys.exit(0)
    else:
        print(f"-- Setting last Git commit timestamp for all files in {target_dir}")

    os.chdir(target_dir)
    timestamp = get_last_commit_timestamp()
    set_file_timestamps(".", timestamp)
    print(f"-- All file timestamps set to: {timestamp}")

if __name__ == "__main__":
    main()
