#!/usr/bin/env python3
"""Generates a fully static python package index from wheel files. See main() below."""

import argparse
import datetime
import difflib
import hashlib
import json
import logging
import os
import shutil
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)


def parse_wheel_filename(filename: str) -> Tuple[str, str, str]:
    parts = filename.split('-')
    if len(parts) < 4:
        raise ValueError("Unexpected wheel filename format: " + filename)
    name, version, python_version = parts[0], parts[1], parts[2]
    return name, version, python_version


def detect_github_pages_url() -> Optional[str]:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo:
        org, name = repo.split('/')
        return f"https://{org}.github.io/{name}"
    return None


def build_static_repo(wheel_dirs: List[str], output_dir: str, base_url: str) -> None:
    out_path = Path(output_dir)
    pkg_dir = out_path / "packages"
    pkg_dir.mkdir(parents=True, exist_ok=True)

    packages: Dict[str, Set[str]] = defaultdict(set)

    for wheel_dir in wheel_dirs:
        path = Path(wheel_dir)
        if not path.exists():
            log.warning(f"Wheel directory not found: {path}")
            continue

        for wheel_path in path.glob("**/*.whl"):
            # Auto-install debug builds with _debug suffix on wheel package name
            new_wheel_path = None
            if wheel_path.parent.name.endswith('-Debug'):
                name, version, _ = parse_wheel_filename(wheel_path.name)
                new_wheel_path = wheel_path.parent / (str(wheel_path.name).replace(name, name + "_debug", 1))
                if not new_wheel_path.exists():
                    shutil.copy2(wheel_path, new_wheel_path)
                wheel_path = new_wheel_path
                
            name, version, _ = parse_wheel_filename(wheel_path.name)
            norm_name = name.lower().replace('_', '-')
            
            if wheel_path.name in packages[norm_name]:
                log.warning(f"Overriding previous wheel with the same name with {wheel_path}...")
            packages[norm_name].add(wheel_path.name)

            dest_path = pkg_dir / wheel_path.name
            if wheel_path != dest_path:
                shutil.copy2(wheel_path, dest_path)
                
            if new_wheel_path is not None:
                new_wheel_path.unlink()
                new_wheel_path = None

    with (out_path / "index.html").open("w") as f_index:
        f_index.write('<!DOCTYPE html><html><head><title>OCP.wasm wheel registry</title></head><body>\n')

        for package, filenames in sorted(packages.items()):
            log.info(f"📦 Processing package {package} with {len(filenames)} wheels found.")
            for fname in sorted(filenames):
                f_index.write(f'<a href="packages/{fname}">{fname}</a><br/>\n')

        f_index.write('</body></html>\n')

    log.info(f"✅ Static PyPI repo generated with {len(packages)} packages and {sum([len(p) for _, p in packages.items()])} wheels.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a fully static python package index from wheel files."
    )
    
    parser.add_argument(
        "--wheels",
        nargs="+",
        required=True,
        help="One or more directories containing .whl files (last takes precedence)"
    )

    base_url_env = detect_github_pages_url()
    parser.add_argument(
        "--base-url",
        default=base_url_env,
        required=base_url_env is None,
        help="Base URL for hosted files (e.g. GitHub Pages). Auto-detected in CI if not provided."
    )
    
    parser.add_argument(
        "--output",
        default="docs",
        help="Output directory for the static repository (default: docs/)"
    )

    args = parser.parse_args()

    build_static_repo(args.wheels, args.output, args.base_url)


if __name__ == "__main__":
    main()
