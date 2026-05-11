#!/usr/bin/env python3
"""Generates a fully static python package index from wheel files."""

import argparse
import logging
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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


def split_version(version: str) -> Tuple[Tuple[int, ...], int]:
    """
    Split versions into:
      (base_version_tuple, post_number)

    Examples:
      1.2.3 -> ((1,2,3), 0)
      1.2.3.post20260511 -> ((1,2,3), 20260511)
    """

    match = re.match(
        r"^([0-9]+(?:\.[0-9]+)*)(?:\.post([0-9]+))?$",
        version
    )

    if not match:
        raise ValueError(f"Unsupported version format: {version}")

    base = tuple(int(x) for x in match.group(1).split('.'))
    post = int(match.group(2) or 0)

    return base, post


def canonical_version(version: str) -> str:
    """Return version without .post suffix."""

    return version.split(".post", 1)[0]


def version_is_newer(version_a: str, version_b: str) -> bool:
    """
    Return True if version_a is newer than version_b.
    """

    base_a, post_a = split_version(version_a)
    base_b, post_b = split_version(version_b)

    if base_a != base_b:
        return base_a > base_b

    return post_a > post_b


def build_static_repo(
    wheel_dirs: List[str],
    output_dir: str,
    base_url: str
) -> None:

    out_path = Path(output_dir)

    # package -> canonical_version -> (full_version, filename)
    packages: Dict[str, Dict[str, Tuple[str, str]]] = defaultdict(dict)

    for wheel_dir in wheel_dirs:
        path = Path(wheel_dir)

        if not path.exists():
            log.warning(f"Wheel directory not found: {path}")
            continue

        for wheel_path in path.glob("**/*.whl"):

            # Auto-install debug builds with _debug suffix
            new_wheel_path = None

            if wheel_path.parent.name.endswith('-Debug'):
                name, version, _ = parse_wheel_filename(wheel_path.name)

                new_wheel_path = wheel_path.parent / (
                    str(wheel_path.name).replace(
                        name,
                        name + "_debug",
                        1
                    )
                )

                if not new_wheel_path.exists():
                    shutil.copy2(wheel_path, new_wheel_path)

                wheel_path = new_wheel_path

            name, version, _ = parse_wheel_filename(wheel_path.name)

            norm_name = name.lower().replace('_', '-')

            canon_version = canonical_version(version)

            existing = packages[norm_name].get(canon_version)

            should_keep = (
                existing is None or
                version_is_newer(version, existing[0])
            )

            if should_keep:

                if existing is not None:
                    log.info(
                        f"Replacing {existing[1]} "
                        f"with newer build {wheel_path.name}"
                    )

                packages[norm_name][canon_version] = (
                    version,
                    wheel_path.name,
                )

                pkg_path = out_path / norm_name
                pkg_path.mkdir(parents=True, exist_ok=True)

                dest_path = pkg_path / wheel_path.name

                if wheel_path != dest_path:
                    shutil.copy2(wheel_path, dest_path)

            if new_wheel_path is not None:
                new_wheel_path.unlink()
                new_wheel_path = None

    with (out_path / "index.html").open("w") as f_index_all:

        f_index_all.write(
            '<!DOCTYPE html>'
            '<html>'
            '<head>'
            '<title>OCP.wasm wheel registry</title>'
            '</head>'
            '<body>\n'
        )

        for package, versions in sorted(packages.items()):

            filenames = sorted(
                item[1]
                for item in versions.values()
            )

            log.info(
                f"📦 Processing package {package} "
                f"with {len(filenames)} wheels kept."
            )

            pkg_path = out_path / package

            with (pkg_path / "index.html").open("w") as f_index:

                f_index.write(
                    '<!DOCTYPE html>'
                    '<html>'
                    '<head>'
                    '<title>OCP.wasm wheel registry</title>'
                    '</head>'
                    '<body>\n'
                )

                for fname in filenames:

                    link = (
                        f'<a href="{base_url}/{package}/{fname}">'
                        f'{fname}</a><br/>\n'
                    )

                    f_index.write(link)
                    f_index_all.write(link)

                f_index.write('</body></html>\n')

        f_index_all.write('</body></html>\n')

    total_wheels = sum(
        len(v)
        for v in packages.values()
    )

    log.info(
        f"✅ Static PyPI repo generated with "
        f"{len(packages)} packages and "
        f"{total_wheels} wheels."
    )


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Generate a fully static python package index "
            "from wheel files."
        )
    )

    parser.add_argument(
        "--wheels",
        nargs="+",
        required=True,
        help=(
            "One or more directories containing .whl files "
            "(last takes precedence)"
        )
    )

    base_url_env = detect_github_pages_url()

    parser.add_argument(
        "--base-url",
        default=base_url_env,
        required=base_url_env is None,
        help=(
            "Base URL for hosted files "
            "(e.g. GitHub Pages). "
            "Auto-detected in CI if not provided."
        )
    )

    parser.add_argument(
        "--output",
        default="docs",
        help=(
            "Output directory for the static repository "
            "(default: docs/)"
        )
    )

    args = parser.parse_args()

    build_static_repo(
        args.wheels,
        args.output,
        args.base_url
    )


if __name__ == "__main__":
    main()