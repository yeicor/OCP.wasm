#!/usr/bin/env python3

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


def fetch_pypi_metadata(package: str) -> Optional[Dict[str, Any]]:
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        log.warning(f"Failed to fetch metadata for {package}: {e}")
        return None


def filter_metadata(
        full_metadata: Dict[str, Any],
        pkg_dir: Path,
        filenames: Set[str],
        base_url: str,
        output_dir: Path
) -> Dict[str, Any]:
    releases = full_metadata.get("releases", {})
    clean_releases: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for fname in filenames:
        log.info(f"    🔍 Gathering basic metadata for {fname}...")
        base_metadata, version = empty_release_metadata(pkg_dir / fname, base_url, output_dir)
        fnames = [artifact["filename"] for _, all_artifacts in releases.items() for artifact in all_artifacts]

        if not fnames:
            log.warning("No release metadata found, saving only basic metadata.")
            matched_meta = base_metadata
        else:
            match = difflib.get_close_matches(fname, fnames, 1, 0)
            if not match:
                log.warning(f"No close match found for {fname}, using basic metadata.")
                matched_meta = base_metadata
            else:
                best_match = match[0]
                matched_meta = next(
                    artifact for _, all_artifacts in releases.items()
                    for artifact in all_artifacts if artifact["filename"] == best_match
                )
                log.info(f"    🔧 Overriding metadata of closest match \"{best_match}\" with our base metadata...")
                matched_meta.update(base_metadata)

        log.debug("    ➕ Merging into release list...")
        clean_releases[version].append(matched_meta)

    full_metadata["releases"] = clean_releases
    full_metadata["urls"] = [artifact for _, artifacts in clean_releases.items() for artifact in artifacts]
    return full_metadata


def empty_release_metadata(file_path: Path, base_url: str, output_dir: Path) -> Tuple[Dict[str, Any], str]:
    with file_path.open("rb") as f:
        data = f.read()

    digests = {
        "blake2b_256": hashlib.blake2b(data, digest_size=32).hexdigest(),
        "md5": hashlib.md5(data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
    }

    size = len(data)
    upload_date_time = datetime.datetime.now(datetime.UTC)
    upload_time = upload_date_time.replace(microsecond=0).isoformat()
    upload_time_iso_8601 = upload_date_time.isoformat() + "Z"

    name, version, python_version = parse_wheel_filename(file_path.name)

    metadata: Dict[str, Any] = {
        "digests": digests,
        "filename": file_path.name,
        "has_sig": False,
        "md5_digest": digests["md5"],
        "packagetype": "bdist_wheel",
        "python_version": python_version,
        "size": size,
        "upload_time": upload_time,
        "upload_time_iso_8601": upload_time_iso_8601,
        "url": f"{base_url}/{file_path.relative_to(output_dir)}",
        "yanked": False,
        "yanked_reason": None
    }
    return metadata, version


def detect_github_pages_url() -> Optional[str]:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo:
        org, name = repo.split('/')
        return f"https://{org}.github.io/{name}"
    return None


def build_static_repo(wheel_dirs: List[str], output_dir: str, base_url: str) -> None:
    out_path = Path(output_dir)
    simple_dir = out_path / "simple"
    pypi_dir = out_path / "pypi"
    pkg_dir = out_path / "packages"

    for d in [simple_dir, pypi_dir, pkg_dir]:
        d.mkdir(parents=True, exist_ok=True)

    packages: Dict[str, Set[str]] = defaultdict(set)

    for wheel_dir in wheel_dirs:
        path = Path(wheel_dir)
        if not path.exists():
            log.warning(f"Wheel directory not found: {path}")
            continue

        for wheel_path in path.glob("**/*.whl"):
            fname = wheel_path.name
            name, version, _ = parse_wheel_filename(fname)

            norm_name = name.lower().replace('_', '-')
            packages[norm_name].add(fname)

            dest_path = pkg_dir / fname
            if wheel_path != dest_path:
                shutil.copy2(wheel_path, dest_path)

    with (simple_dir / "index.html").open("w") as f_index:
        f_index.write('<!DOCTYPE html><html><head><title>OCP.wasm PyPI-like wheel registry</title></head><body>\n')

        for package, filenames in sorted(packages.items()):
            log.info(f"📦 Processing package: {package}")
            pypi_pkg_dir = pypi_dir / package
            pypi_pkg_dir.mkdir(parents=True, exist_ok=True)

            for fname in sorted(filenames):
                f_index.write(f'<a href="../packages/{fname}">{fname}</a><br/>\n')

            log.info("  🌐 Fetching package metadata...")
            real_metadata = fetch_pypi_metadata(package)
            if not real_metadata:
                log.warning(f"  Skipping {package} due to metadata fetch failure.")
                continue

            log.info("  🧬 Recreating package metadata...")
            filtered_json = filter_metadata(real_metadata, pkg_dir, filenames, base_url, out_path)

            with (pypi_pkg_dir / "json").open("w") as f_json:
                json.dump(filtered_json, f_json, indent=2)

        f_index.write('</body></html>\n')

    log.info("✅ Static PyPI repo generated.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a fully static PyPI mirror with JSON API from wheel files."
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
