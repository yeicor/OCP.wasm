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
import tempfile
import zipfile
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


def create_renamed_wheel(original_wheel: Path, new_name: str) -> Path:
    """Create a new wheel with modified package name in metadata."""
    name, version, _ = parse_wheel_filename(original_wheel.name)
    new_wheel_name = original_wheel.name.replace(name, new_name, 1)
    new_wheel_path = original_wheel.parent / new_wheel_name
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Extract the original wheel
        with zipfile.ZipFile(original_wheel, 'r') as zip_in:
            zip_in.extractall(tmpdir_path)
        
        # Modify the METADATA file
        dist_info_dirs = list(tmpdir_path.glob('*.dist-info'))
        if dist_info_dirs:
            old_dist_info = dist_info_dirs[0]
            metadata_file = old_dist_info / 'METADATA'
            
            if metadata_file.exists():
                # Read and modify metadata
                content = metadata_file.read_text()
                lines = content.split('\n')
                new_lines = []
                for line in lines:
                    if line.startswith('Name:'):
                        new_lines.append(f'Name: {new_name}')
                    else:
                        new_lines.append(line)
                metadata_file.write_text('\n'.join(new_lines))
            
            # Rename .dist-info directory
            new_dist_info_name = new_wheel_name.rsplit('-', 3)[0] + '.dist-info'
            new_dist_info = tmpdir_path / new_dist_info_name
            old_dist_info.rename(new_dist_info)
            
            # Update RECORD file if it exists
            record_file = new_dist_info / 'RECORD'
            if record_file.exists():
                content = record_file.read_text()
                content = content.replace(str(old_dist_info.name), new_dist_info_name)
                record_file.write_text(content)
        
        # Repack the wheel
        with zipfile.ZipFile(new_wheel_path, 'w', zipfile.ZIP_DEFLATED) as zip_out:
            for file in tmpdir_path.rglob('*'):
                if file.is_file():
                    arcname = file.relative_to(tmpdir_path)
                    zip_out.write(file, arcname)
    
    return new_wheel_path


def build_static_repo(wheel_dirs: List[str], output_dir: str, base_url: str) -> None:
    out_path = Path(output_dir)

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
                new_wheel_path = create_renamed_wheel(wheel_path, name + "_debug")
                wheel_path = new_wheel_path
            
            # Create -novtk alias for cadquery-ocp wheels
            name, version, _ = parse_wheel_filename(wheel_path.name)
            if name == "cadquery-ocp" or name == "cadquery_ocp":
                novtk_wheel_path = create_renamed_wheel(wheel_path, "cadquery-ocp-novtk")
                novtk_name = "cadquery-ocp-novtk"
                norm_novtk_name = novtk_name.lower().replace('_', '-')
                packages[norm_novtk_name].add(novtk_wheel_path.name)
                
                pkg_path = out_path / norm_novtk_name
                pkg_path.mkdir(parents=True, exist_ok=True)
                dest_path = pkg_path / novtk_wheel_path.name
                if novtk_wheel_path != dest_path:
                    shutil.copy2(novtk_wheel_path, dest_path)
                novtk_wheel_path.unlink()
                
            norm_name = name.lower().replace('_', '-')
            
            if wheel_path.name in packages[norm_name]:
                log.warning(f"Overriding previous wheel with the same name with {wheel_path}...")
            packages[norm_name].add(wheel_path.name)

            pkg_path = out_path / norm_name
            pkg_path.mkdir(parents=True, exist_ok=True)
            dest_path = pkg_path / wheel_path.name
            if wheel_path != dest_path:
                shutil.copy2(wheel_path, dest_path)
                
            if new_wheel_path is not None:
                new_wheel_path.unlink()
                new_wheel_path = None

    with (out_path / "index.html").open("w") as f_index_all:
        f_index_all.write('<!DOCTYPE html><html><head><title>OCP.wasm wheel registry</title></head><body>\n')

        for package, filenames in sorted(packages.items()):
            log.info(f"📦 Processing package {package} with {len(filenames)} wheels found.")
            pkg_path = out_path / package
            
            with (pkg_path / "index.html").open("w") as f_index:
                
                f_index.write('<!DOCTYPE html><html><head><title>OCP.wasm wheel registry</title></head><body>\n')
                
                for fname in sorted(filenames):
                    link = f'<a href="{base_url}/{package}/{fname}">{fname}</a><br/>\n'
                    f_index.write(link)
                    f_index_all.write(link)
                    
                f_index.write('</body></html>\n')

        f_index_all.write('</body></html>\n')

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