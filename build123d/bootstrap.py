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


async def _platform_install(pkg, reinstall=False):
    """Platform-independent install for a package string."""
    logger.info(f"Installing package: {pkg} (reinstall={reinstall})")
    if sys.platform == "emscripten":
        if micropip is None:
            logger.error("micropip is not available in this environment")
            raise RuntimeError("micropip is not available in this environment")
        await micropip.install(pkg, reinstall=reinstall)
        logger.debug(f"micropip installed {pkg}")
    else:
        import subprocess

        args = [sys.executable, "-m", "pip", "install"]
        if reinstall:
            args.append("--force-reinstall")
        args.append(pkg)
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


def _parse_version_spec(spec_str):
    """Parse version specifier and return the best mock version."""
    upper = None
    lower_bounds = []

    for part in spec_str.split(","):
        part = part.strip()
        if part.startswith("<="):
            v = part[2:].strip()
            if upper is None or v < upper:
                upper = v
        elif part.startswith("<"):
            v = part[1:].strip()
            if upper is None or v < upper:
                upper = v
        elif part.startswith(">="):
            lower_bounds.append(part[2:].strip())
        elif part.startswith(">"):
            lower_bounds.append(part[1:].strip())
        elif part.startswith("~="):
            lower_bounds.append(part[2:].strip())
        elif part.startswith("=="):
            lower_bounds.append(part[2:].strip())

    if not lower_bounds:
        return None

    highest_lower = max(lower_bounds)
    if upper:
        return highest_lower + ".9999999999"
    return highest_lower


def _extract_version_specs(requires_dist):
    """Extract version specifications from requirements list, supporting variant namings."""
    mock_versions = {}
    ocp_specifiers = {}

    # Acceptable variants for OCP packages
    ocp_variants = [
        ("cadquery-ocp-novtk", ["cadquery-ocp", "cadquery-ocp-novtk"]),
        ("lib3mf", ["lib3mf", "py-lib3mf"]),
    ]

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
    try:
        data = await _get_pypi_json(package_name)
        releases = data.get("releases", {})
        logger.debug(f"Found versions for {package_name}: {list(releases.keys())}")

        # Only consider .dev versions that match the version_spec
        # version_spec may be empty or something like '>=0.9,<0.10'
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
            # Fallback: no dev versions available, return empty spec
            logger.warning(
                f"No .dev versions found for {package_name} matching spec {version_spec}"
            )
            return ""

        # Sort versions using packaging.version
        dev_versions.sort(key=packaging.version.parse, reverse=True)

        # Return the latest .dev version
        logger.info(f"Using .dev version for {package_name}: {dev_versions[0]}")
        return f"=={dev_versions[0]}"
    except Exception as e:
        logger.warning(f"Could not query PyPI for {package_name} dev versions: {e}")
        return ""


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
    # Define OCP packages to install with their specs and mock names
    ocp_packages = [
        ("lib3mf-OCP.wasm", ["lib3mf", "py-lib3mf"]),
        ("cadquery-ocp-novtk-OCP.wasm", ["cadquery-ocp"]),
    ]

    mocked_packages = []
    for wheel_pkg, mock_names in ocp_packages:
        spec = ocp_specifiers[wheel_pkg.replace("-OCP.wasm", "")]
        if debug:  # Replace with ==.dev... if available, as this is the only way to get a prerelease
            spec = await _find_latest_dev_version(wheel_pkg, spec)
        await _platform_install(f"{wheel_pkg}{spec}", reinstall=True)

        if sys.platform == "emscripten" and micropip is not None:
            version = importlib.metadata.version(wheel_pkg)
            for mock_name in mock_names:
                logger.debug(f"Adding mock package {mock_name} for Pyodide")
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
        await _platform_install("sqlite3", reinstall=True)

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
    await _platform_install(f"build123d=={version}", reinstall=True)


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


async def _install_from_github(build123d_ref):
    """Download build123d from GitHub as zip, extract, patch, and install dependencies."""
    import tomllib

    # Download zip file from GitHub
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

    # Extract zip
    _tmpdir = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(file=io.BytesIO(sources_bytes), mode="r") as zipf:
        zipf.extractall(path=_tmpdir.name)

    # Find extracted directory (GitHub creates build123d-<ref> directory)
    extracted_dirs = os.listdir(_tmpdir.name)
    _extracted_dir = os.path.join(_tmpdir.name, extracted_dirs[0])
    _sources_folder = os.path.join(_extracted_dir, "src")
    sys.path.insert(0, _sources_folder)

    # Patch pyproject.toml
    pyproject_path = os.path.join(_extracted_dir, "pyproject.toml")
    with open(pyproject_path, "r") as f:
        pyproject_content = f.read()

    version = build123d_ref.strip("v")
    if re.match(r"^\d+\.\d+\.\d+$", version) is None:
        version = "0.0.0+" + version.replace(".", "_").replace("/", "_")
    pyproject_content = re.sub(
        r'dynamic = \["version"]', 'version = "' + version + '"', pyproject_content
    )
    pyproject_content = re.sub(r'"setuptools_scm.*?",', "", pyproject_content)
    pyproject_content = re.sub(
        r"\[tool\.setuptools.*]\n([^\[].*?\n)*", "", pyproject_content
    )

    with open(pyproject_path, "w") as f:
        f.write(pyproject_content)

    # Patch __init__.py
    init_path = os.path.join(_sources_folder, "build123d", "__init__.py")
    with open(init_path, "r") as f:
        init_content = f.read()

    init_content = re.sub(
        r"from \.version import version as __version__",
        f"__version__ = '{version}'",
        init_content,
    )

    with open(init_path, "w") as f:
        f.write(init_content)

    # Parse dependencies
    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)

    _dependencies = pyproject_data.get("project", {}).get("dependencies", [])
    if os.getenv("_install_build123d_from_github_also_optional", "") != "":
        _dependencies += (
            pyproject_data.get("project", {})
            .get("optional-dependencies", {})
            .get("development", [])
        )
        _dependencies += (
            pyproject_data.get("project", {})
            .get("optional-dependencies", {})
            .get("benchmark", [])
        )

    # Install dependencies
    logger.info(f"Installing dependencies: {_dependencies}")
    for dep in _dependencies:
        dep = dep.strip()
        if (
            not dep
            or dep.startswith("lib3mf")
            or dep.startswith("cadquery-ocp")
            or dep == "mypy"
        ):
            logger.debug(f"Skipping dependency: {dep}")
            continue
        logger.info(f"Installing dependency: {dep}")
        await _platform_install(dep, reinstall=True)

    return _tmpdir, _extracted_dir


async def bootstrap(build123d_ref="stable", debug=False):
    """Bootstrap build123d for testing.

    Works in both native and Pyodide environments.

    Args:
        build123d_ref: "stable" (latest PyPI), "vX.Y.Z" (PyPI version), GitHub ref, or custom version
        debug: If True, use debug OCP.wasm wheels (.dev* suffix) instead of release versions (.post* suffix)

    Returns:
        (tmpdir, extracted_dir): tmpdir for cleanup, extracted_dir for use (None if installed from PyPI)
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

    # Try PyPI first as user can always override with a github: prefix if they want to test against the latest sources
    is_pypi_ref = False
    if not build123d_ref.startswith("github:"):
        try:
            logger.debug(f"Gathering dependency specifiers from PyPI: {build123d_ref}")
            ocp_specifiers = await _get_pypi_version(build123d_ref)
            is_pypi_ref = True
            logger.debug(f"Found build123d version {build123d_ref} on PyPI")
        except Exception as e:
            logger.debug(
                f"Could not find build123d version {build123d_ref} on PyPI: {e}. Will try GitHub."
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
        tmpdir, extracted_dir = None, None
    else:
        logger.debug(
            f"Installing build123d from GitHub sources version {build123d_ref}"
        )
        tmpdir, extracted_dir = await _install_from_github(build123d_ref)

    # Clean up mocked packages before returning
    await cleanup_mocks()

    logger.debug(f"Bootstrap complete. tmpdir={tmpdir}, extracted_dir={extracted_dir}")
    return tmpdir, extracted_dir
