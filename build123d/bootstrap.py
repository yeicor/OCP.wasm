import asyncio
import importlib.metadata
import io
import json
import logging
import os
import re
import sys
import tempfile
import zipfile

# Set up logger
logger = logging.getLogger("build123d_bootstrap")
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
handler.setFormatter(formatter)
if not logger.hasHandlers():
    logger.addHandler(handler)

try:
    import micropip  # type: ignore
except ModuleNotFoundError:
    micropip = None

try:
    from pyodide.http import pyfetch  # type: ignore
except ModuleNotFoundError:
    pyfetch = None


class _NormalizedResponse:
    """Wrapper to normalize responses from pyfetch (Pyodide) and urllib (native Python)."""

    def __init__(self, response, is_emscripten):
        self._response = response
        self._is_emscripten = is_emscripten

    @property
    def status(self):
        """Get HTTP status code (works for both platforms)."""
        if self._is_emscripten:
            return self._response.status
        else:
            return self._response.code

    def get_header(self, name):
        """Get HTTP header value (works for both platforms)."""
        if self._is_emscripten:
            return self._response.headers.get(name)
        else:
            return self._response.getheader(name)

    async def text(self):
        """Get response body as text (works for both platforms)."""
        if self._is_emscripten:
            return await self._response.text()
        else:
            return self._response.read().decode("utf-8")

    async def bytes(self):
        """Get response body as bytes (works for both platforms)."""
        if self._is_emscripten:
            return await self._response.bytes()
        else:
            return self._response.read()

    async def json(self):
        """Get response body as JSON (works for both platforms)."""
        if self._is_emscripten:
            return await self._response.json()
        else:
            return json.load(self._response)


async def _fetch(url):
    """Fetch URL content. Returns normalized response (same interface for both platforms)."""
    is_emscripten = sys.platform == "emscripten"
    logger.debug(
        f"Fetching URL: {url} (platform: {'Pyodide' if is_emscripten else 'native'})"
    )

    if is_emscripten:
        if pyfetch is None:
            logger.error("pyfetch not available in Pyodide environment")
            raise RuntimeError("pyfetch not available in Pyodide environment")
        try:
            response = await pyfetch(url)
        except Exception as e:  # pyodide.http._exceptions.AbortError
            logger.warning(f"pyfetch failed for {url}: {e}. Retrying with CORS proxy.")
            import urllib.parse

            url = (
                "https://little-hill-4bc4.yeicor-cloudflare.workers.dev/?url="
                + urllib.parse.quote_plus(url)
            )
            response = await pyfetch(url)
    else:
        import urllib.request

        logger.debug(f"Using urllib to fetch {url}")
        response = urllib.request.urlopen(url)

    logger.debug(
        f"Fetched {url} with status {response.status if is_emscripten else response.code}"
    )
    return _NormalizedResponse(response, is_emscripten)


async def _fetch_bytes(url):
    """Fetch URL and return bytes, following redirects."""
    max_redirects = 5
    for i in range(max_redirects):
        logger.debug(f"_fetch_bytes: Attempt {i + 1} for {url}")
        response = await _fetch(url)
        status = response.status
        logger.debug(f"_fetch_bytes: Status {status} for {url}")
        if 300 <= status < 400:
            location = response.get_header("Location")
            logger.info(f"Redirect {url} -> {location}")
            if not location:
                logger.error(f"Redirect with no Location header for {url}")
                raise RuntimeError(f"Redirect with no Location header for {url}")
            url = location
            continue
        if 200 <= status < 300:
            logger.debug(f"_fetch_bytes: Success for {url}")
            return await response.bytes()
        logger.error(f"Failed to fetch {url}: HTTP {status}")
        raise RuntimeError(f"Failed to fetch {url}: HTTP {status}")
    logger.error(f"Too many redirects while fetching {url}")
    raise RuntimeError(f"Too many redirects while fetching {url}")


async def _platform_install(pkg):
    """Platform-independent install for a package string (always forces reinstall)."""
    logger.info(f"Installing package: {pkg}")
    if sys.platform == "emscripten":
        if micropip is None:
            logger.error("micropip is not available in this environment")
            raise RuntimeError("micropip is not available in this environment")
        await micropip.install(pkg, reinstall=True, keep_going=True)
        logger.debug(f"micropip installed {pkg}")
    else:
        import subprocess

        args = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--force-reinstall",
        ] + pkg.split(" ")
        logger.debug(f"Running pip install: {' '.join(args)}")
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        logger.debug(f"pip stdout: {stdout.decode()}")
        if process.returncode != 0:
            logger.error(f"Failed to install package {pkg}:\n{stderr.decode()}")
            raise Exception(f"Failed to install package {pkg}:\n{stderr.decode()}")
        logger.debug(f"pip installed {pkg}")


# Acceptable variants for OCP packages
ocp_variants = [
    ("cadquery-ocp-novtk", ["cadquery-ocp", "cadquery-ocp-novtk"]),
    ("lib3mf", ["lib3mf", "py-lib3mf"]),
]


def _is_version_specifier(ref):
    """Check if ref looks like a version specifier (e.g., '<0.11,>=0.10') vs a tag/branch."""
    # Version specifiers contain operators like >=, <=, ==, ~=, >, <
    return any(op in ref for op in [">=", "<=", "==", "~=", ">", "<"])


def _extract_version_specs(requires_dist):
    """Extract version specifications from requirements list, supporting variant namings."""
    mock_versions = {}
    ocp_specifiers = {}

    for req in requires_dist:
        req = req.replace("(", "").replace(")", "").strip()
        if not req:
            continue

        if ";" in req:  # Strip environment markers (everything after semicolon)
            req = req.split(";")[0].strip()

        for canonical, variants in ocp_variants:
            for variant in variants:
                req_name = re.split(r">=|>|<=|<|~=|==", req)[0].strip()
                # logger.debug(f"Checking if '{req_name}' matches variant '{variant}' for canonical '{canonical}'")
                if req_name == variant:
                    # Get the suffix (version specifier and extras, if any)
                    suffix = req[len(variant) :].lstrip()
                    logger.debug(
                        f"Matched variant '{variant}' for canonical '{canonical}', suffix: '{suffix}'"
                    )
                    ocp_specifiers[canonical] = suffix
                    break

    logger.debug(f"Extracted ocp_specifiers: {ocp_specifiers}")
    return mock_versions, ocp_specifiers


async def _resolve_version_specifier(version_spec):
    """Resolve a version specifier (e.g., '<0.11,>=0.10') to the best matching PyPI version.

    Returns the resolved version string (e.g., 'v0.10.5') or raises an exception if no match found.
    """
    logger.info(f"Resolving version specifier: {version_spec}")

    if not version_spec or version_spec == "":
        logger.warning("Empty version specifier, using latest stable")
        data = await _get_pypi_json("build123d")
        return data["info"]["version"]

    # If it's not a specifier, assume it's a concrete version or ref
    if not _is_version_specifier(version_spec):
        logger.debug(
            f"'{version_spec}' is not a specifier, treating as concrete version/ref"
        )
        return version_spec

    # Parse the specifier
    await _platform_install("packaging")
    import packaging.specifiers
    import packaging.version

    try:
        spec_set = packaging.specifiers.SpecifierSet(version_spec)
    except Exception as e:
        logger.error(f"Invalid version specifier: {version_spec}: {e}")
        raise ValueError(f"Invalid version specifier: {version_spec}") from e

    # Fetch all versions from PyPI
    data = await _get_pypi_json("build123d")
    releases = data.get("releases", {})

    if not releases:
        logger.error("No releases found on PyPI for build123d")
        raise RuntimeError("No releases found on PyPI for build123d")

    # Find versions matching the specifier, sorted from latest to earliest
    matching_versions = []
    for v in releases.keys():
        try:
            parsed = packaging.version.parse(v)
            # Skip pre-releases and dev versions unless explicitly requested
            if parsed in spec_set:
                matching_versions.append((parsed, v))
        except Exception as e:
            logger.debug(f"Could not parse version {v}: {e}")
            continue

    if not matching_versions:
        logger.error(f"No versions found matching specifier: {version_spec}")
        raise RuntimeError(f"No versions found on PyPI matching {version_spec}")

    # Sort by parsed version, descending (latest first)
    matching_versions.sort(key=lambda x: x[0], reverse=True)
    best_version = matching_versions[0][1]

    logger.info(f"Resolved version specifier '{version_spec}' to '{best_version}'")
    return best_version


async def _get_pypi_json(package, version=None):
    """Fetch package metadata from PyPI."""
    url = f"https://pypi.org/pypi/{package}"
    if version:
        url += f"/{version}"
    url += "/json"
    logger.info(f"Fetching PyPI JSON for {package} (version={version})")
    response = await _fetch(url)
    data = await response.json()
    logger.debug(f"Fetched PyPI JSON for {package}: {list(data.keys())}")
    return data


async def _find_latest_dev_version(package_name, version_spec):
    """Query PyPI to find the latest .dev version matching the version spec."""
    logger.info(
        f"Looking for latest .dev version for {package_name} (spec: {version_spec})"
    )
    data = await _get_pypi_json(package_name)
    releases = data.get("releases", {})
    logger.debug(f"Found versions for {package_name}: {list(releases.keys())}")

    # Only consider .dev versions that match the version_spec
    # version_spec may be empty or something like '>=0.9,<0.10'
    await _platform_install("packaging")
    import packaging.specifiers
    import packaging.version

    spec = packaging.specifiers.SpecifierSet(version_spec) if version_spec else None
    dev_versions = []
    for v in releases.keys():
        if ".dev" in v:
            try:
                ver = packaging.version.parse(v)
                if spec is None or ver in spec:
                    dev_versions.append(v)
            except Exception:
                continue
    logger.debug(
        f"Found .dev versions for {package_name} matching spec: {dev_versions}"
    )
    if not dev_versions:
        # Fallback: no dev versions available, return original spec to at least get the latest stable version
        logger.warning(
            f"No .dev versions found for {package_name} matching spec {version_spec}"
        )
        return version_spec

    # Sort versions using packaging.version
    dev_versions.sort(key=packaging.version.parse, reverse=True)

    # Return the latest .dev version
    logger.info(f"Using .dev version for {package_name}: {dev_versions[0]}")
    return f"=={dev_versions[0]}"


async def _get_pypi_version(build123d_ref):
    """Fetch build123d dependencies from PyPI."""
    logger.debug(f"Fetching build123d dependencies from PyPI (version={build123d_ref})")
    data = await _get_pypi_json("build123d", build123d_ref)
    requires_dist = data["info"].get("requires_dist", [])
    _, ocp_specifiers = _extract_version_specs(requires_dist)
    return ocp_specifiers


async def _install_and_mock_ocp_wasm_wheels(ocp_specifiers, debug=False):
    """Install OCP WASM wheels. If debug=True, prefer .dev versions.

    Returns a cleanup function that removes all mocked packages.
    """
    logger.info(
        f"Installing OCP WASM wheels (debug={debug}) with specifiers: {ocp_specifiers}"
    )

    mocked_packages = []
    for canonical_name, mock_names in ocp_variants:
        spec = ocp_specifiers[canonical_name]
        my_pkg_name = canonical_name + "-OCP.wasm"
        if debug:  # Replace with ==.dev... if available, as this is the only way to get a prerelease
            spec = await _find_latest_dev_version(my_pkg_name, spec)
        await _platform_install(f"{my_pkg_name}{spec}")

        if sys.platform == "emscripten" and micropip is not None:
            version = importlib.metadata.version(my_pkg_name)
            for mock_name in mock_names:
                logger.debug(f"Adding mock package {mock_name}=={version} for Pyodide")
                mocked_packages.append(mock_name)
                if mock_name == "py-lib3mf":
                    micropip.add_mock_package(
                        mock_name,
                        version,
                        modules={"py_lib3mf": "from lib3mf import *"},
                    )
                else:
                    micropip.add_mock_package(mock_name, version)

    if sys.platform == "emscripten":
        logger.debug("Installing sqlite3 for emscripten platform")
        await _platform_install("sqlite3")

    async def cleanup_mocks():
        """Remove all mocked packages."""
        if sys.platform == "emscripten" and micropip is not None:
            for mock_name in mocked_packages:
                logger.debug(f"Removing mock package {mock_name}")
                micropip.remove_mock_package(mock_name)

    return cleanup_mocks


async def _install_from_pypi(version):
    """Install build123d from PyPI."""
    logger.info(f"Installing build123d from PyPI version {version}")
    await _platform_install(f"build123d=={version}")


async def _get_github_version(ref_name):
    """Fetch build123d dependencies from GitHub."""
    logger.debug(f"Fetching build123d dependencies from GitHub (ref={ref_name})")
    resp = await _fetch(
        f"https://raw.githubusercontent.com/gumyr/build123d/{ref_name}/pyproject.toml"
    )
    if resp.status != 200:
        error_msg = f"Failed to fetch pyproject.toml for {ref_name}: HTTP {resp.status}"
        raise RuntimeError(error_msg)
    content = await resp.text()

    import tomllib

    try:
        deps = tomllib.loads(content).get("project", {}).get("dependencies", [])
    except Exception as e:
        raise RuntimeError(
            f"Failed to parse pyproject.toml for {ref_name}: {e}\n"
            f"Content received: {content[:200]}..."
        ) from e
    _, ocp_specifiers = _extract_version_specs(deps)
    return ocp_specifiers


def _find_build123d_sources():
    """Find the build123d sources directory in site-packages."""
    import site

    site_packages_dirs = site.getsitepackages() + [site.getusersitepackages()]
    for site_pkg in site_packages_dirs:
        src_path = os.path.join(site_pkg, "build123d-src")
        if os.path.isdir(src_path):
            return src_path
        src_path = os.path.join(site_pkg, "build123d")
        if os.path.isdir(src_path):
            return src_path
    return None


async def _install_from_github(build123d_ref):
    """Download and install build123d from GitHub."""
    import shutil

    import tomllib

    # Download and extract
    zip_url = f"https://github.com/gumyr/build123d/archive/{build123d_ref}.zip"
    logger.debug(f"Downloading {zip_url}...")
    try:
        sources_bytes = await _fetch_bytes(zip_url)
    except RuntimeError as e:
        if "HTTP 404" in str(e):
            raise RuntimeError(
                f"Failed to download build123d from GitHub: the ref '{build123d_ref}' does not exist."
            ) from e
        raise

    tmpdir = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(file=io.BytesIO(sources_bytes), mode="r") as zipf:
        zipf.extractall(path=tmpdir.name)

    extracted_dir = os.path.join(tmpdir.name, os.listdir(tmpdir.name)[0])
    sources_folder = os.path.join(extracted_dir, "src")

    # Determine version
    version_match = re.match(r"^v?(\d+\.\d+\.\d)+$", build123d_ref)
    if version_match is not None:
        version = version_match.group(1)
    else:
        try:
            data = await _get_pypi_json("build123d")
            latest_version = data["info"]["version"]
            version = (
                latest_version + "+" + build123d_ref.replace(".", "_").replace("/", "_")
            )
        except Exception as e:
            logger.warning(f"Could not fetch latest stable version: {e}")
            version = "0.0.0+" + build123d_ref.replace(".", "_").replace("/", "_")


    # Patch pyproject.toml and __init__.py
    pyproject_path = os.path.join(extracted_dir, "pyproject.toml")
    with open(pyproject_path, "r") as f:
        content = f.read()
    content = re.sub(r'dynamic = \["version"]', f'version = "{version}"', content)
    content = re.sub(r'"setuptools_scm.*?",', "", content)
    content = re.sub(r"\[tool\.setuptools.*]\n([^\[].*?\n)*", "", content)
    with open(pyproject_path, "w") as f:
        f.write(content)

    init_path = os.path.join(sources_folder, "build123d", "__init__.py")
    with open(init_path, "r") as f:
        content = f.read()
    content = re.sub(
        r"from \.version import version as __version__",
        f"__version__ = '{version}'",
        content,
    )
    with open(init_path, "w") as f:
        f.write(content)

    # Parse and install dependencies
    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)

    deps = pyproject_data.get("project", {}).get("dependencies", [])
    if os.getenv("_install_build123d_from_github_also_optional", "") != "":
        deps += (
            pyproject_data.get("project", {})
            .get("optional-dependencies", {})
            .get("development", [])
        )
        deps += (
            pyproject_data.get("project", {})
            .get("optional-dependencies", {})
            .get("benchmark", [])
        )

    for dep in deps:
        dep = dep.strip()
        if (
            not dep
            or dep.startswith("lib3mf")
            or dep.startswith("cadquery-ocp")
            or dep == "mypy"
        ):
            continue
        await _platform_install(dep)

    if sys.platform == "emscripten":
        import site

        site_packages = site.getsitepackages()[0]
        dest_base = os.path.join(site_packages, "build123d-src")
        dest_src = os.path.join(dest_base, "src")
        os.makedirs(dest_src, exist_ok=True)

        # Copy build123d package
        shutil.rmtree(os.path.join(dest_src, "build123d"), ignore_errors=True)
        shutil.copytree(
            os.path.join(sources_folder, "build123d"),
            os.path.join(dest_src, "build123d"),
        )

        # Copy test files and other artifacts
        for item in os.listdir(extracted_dir):
            if item not in ("src", ".git", ".gitignore"):
                src = os.path.join(extracted_dir, item)
                dst = os.path.join(dest_base, item)
                if os.path.isdir(src):
                    shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

        sys.path.insert(0, dest_src)

        # Create dist-info metadata
        dist_info_dir = os.path.join(site_packages, f"build123d-{version}.dist-info")
        os.makedirs(dist_info_dir, exist_ok=True)
        for fname, content in [
            (
                "METADATA",
                f"Metadata-Version: 2.1\nName: build123d\nVersion: {version}\n",
            ),
            (
                "WHEEL",
                "Wheel-Version: 1.0\nGenerator: build123d-bootstrap\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            ),
            ("RECORD", ""),
            ("entry_points.txt", ""),
        ]:
            with open(os.path.join(dist_info_dir, fname), "w") as f:
                f.write(content)
        logger.info(f"Installed build123d sources to {dest_base}")
    else:
        await _platform_install(f"-e {extracted_dir}")

    # Cleanup temporary directory
    tmpdir.cleanup()


async def bootstrap(build123d_ref="stable", debug=False, mocked_hook=None):
    """Bootstrap build123d for testing.

    Works in both native and Pyodide environments.

    Args:
        build123d_ref: "stable" (latest PyPI), "vX.Y.Z" (PyPI version), version specifier
                       (e.g., "<0.11,>=0.10"), GitHub ref, or custom version.
                       Prefix with "github:" to force GitHub sources.
        debug: If True, use debug OCP.wasm wheels (.dev* suffix) instead of release versions

    Returns:
        Path to build123d directory (sources for GitHub installs and wheel contents for PyPI installs).

    Raises:
        RuntimeError: If version cannot be resolved or installation fails.
        ValueError: If version specifier is invalid.
    """
    logger.debug(f"Bootstrapping build123d (ref={build123d_ref}, debug={debug})")

    # Handle "stable" by fetching latest version
    if build123d_ref == "stable" or build123d_ref == "github:stable":
        logger.debug("Fetching latest version for build123d from PyPI")
        data = await _get_pypi_json("build123d")
        if build123d_ref == "stable":
            build123d_ref = data["info"]["version"]
        else:
            build123d_ref = "github:v" + data["info"]["version"]
        logger.debug(f"Latest build123d version: {build123d_ref}")

    # Check if it's a version specifier that needs resolution
    force_github = build123d_ref.startswith("github:")
    ref_to_check = (
        build123d_ref[len("github:") :]
        if force_github
        else build123d_ref
    )

    # If it's a version specifier (e.g., "<0.11,>=0.10"), resolve it to a concrete version
    if _is_version_specifier(ref_to_check) and not force_github:
        logger.info(f"Version specifier detected: {ref_to_check}. Resolving to concrete version...")
        try:
            resolved_version = await _resolve_version_specifier(ref_to_check)
            logger.info(f"Resolved '{ref_to_check}' to '{resolved_version}'")
            build123d_ref = resolved_version
        except Exception as e:
            logger.error(f"Failed to resolve version specifier '{ref_to_check}': {e}")
            raise RuntimeError(
                f"Could not resolve version specifier '{ref_to_check}': {e}\n"
                f"Try specifying a concrete version like 'v0.10.5' or '0.10.5'"
            ) from e

    # Try PyPI first as user can always override with a github: prefix if they want to test against the latest sources
    is_pypi_ref = False
    ocp_specifiers = None

    if not build123d_ref.startswith("github:"):
        try:
            logger.debug(f"Gathering dependency specifiers from PyPI: {build123d_ref}")d build123d version {build123d_ref} on PyPI: {e}. Will try GitHub."
            )

    # Get dependencies and install OCP wheels
    if not is_pypi_ref:
        build123d_ref = (
            build123d_ref[len("github:") :]
            if build123d_ref.startswith("github:")
            else build123d_ref
        )
        logger.debug(
            f"Installing build123d from GitHub sources with ref: {build123d_ref}"
        )
        ocp_specifiers = await _get_github_version(build123d_ref)

    logger.debug(f"Using OCP specifiers {ocp_specifiers} to install OCP WASM wheels")
    cleanup_mocks = await _install_and_mock_ocp_wasm_wheels(ocp_specifiers, debug=debug)

    if is_pypi_ref:
        logger.debug(f"Installing build123d from PyPI wheels version {build123d_ref}")
        await _install_from_pypi(build123d_ref)
    else:
        logger.debug(
            f"Installing build123d from GitHub sources version {build123d_ref}"
        )
        await _install_from_github(build123d_ref)

    # Clean up mocked packages before returning
    await cleanup_mocks()

    sources = _find_build123d_sources()
    logger.debug(f"Bootstrap complete. sources={sources}")
    return sources
