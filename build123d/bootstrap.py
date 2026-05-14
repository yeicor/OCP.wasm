import importlib.metadata
import io
import os
import re
import sys
import tempfile
import zipfile

try:
    import micropip
except ModuleNotFoundError:
    pass

try:
    from pyodide.http import pyfetch
except ModuleNotFoundError:
    pyfetch = None


def _select_mock_version(spec_str):
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


def _parse_dep_requirements(requires_dist):
    mock_versions = {}
    ocp_specifiers = {}

    for req in requires_dist:
        req = req.replace("(", "").replace(")", "")
        for pkg_name in ("cadquery-ocp-novtk", "cadquery-ocp", "lib3mf"):
            if req.startswith(pkg_name):
                suffix = req[len(pkg_name) :].lstrip()
                if not suffix or suffix[0] not in (">", "<", "=", "~", "!", "("):
                    continue
                version = _select_mock_version(suffix)
                if version:
                    if (
                        pkg_name not in mock_versions
                        or version > mock_versions[pkg_name]
                    ):
                        mock_versions[pkg_name] = version
                        ocp_specifiers[pkg_name] = suffix
                break

    if "cadquery-ocp" in mock_versions and "cadquery-ocp-novtk" not in mock_versions:
        mock_versions["cadquery-ocp-novtk"] = mock_versions["cadquery-ocp"]
        ocp_specifiers["cadquery-ocp-novtk"] = ocp_specifiers.get("cadquery-ocp", "")
    if "cadquery-ocp-novtk" in mock_versions and "cadquery-ocp" not in mock_versions:
        mock_versions["cadquery-ocp"] = mock_versions["cadquery-ocp-novtk"]
        ocp_specifiers["cadquery-ocp"] = ocp_specifiers.get("cadquery-ocp-novtk", "")

    return mock_versions, ocp_specifiers


async def _fetch(url):
    """Fetch URL content. Native uses urllib, Pyodide uses pyfetch with CORS proxy."""
    if sys.platform == "emscripten":
        if pyfetch is None:
            raise RuntimeError("pyfetch not available in Pyodide environment")
        try:
            response = await pyfetch(url)
        except Exception as e:  # pyodide.http._exceptions.AbortError
            # Assume CORS error and try proxy instead
            url = "https://little-hill-4bc4.yeicor-cloudflare.workers.dev/?url=" + url
            response = await pyfetch(url)
        return response
    else:
        import urllib.request

        return urllib.request.urlopen(url)


async def _is_github_ref(owner, repo, ref):
    for url in (
        f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{ref}",
        f"https://api.github.com/repos/{owner}/{repo}/git/ref/tags/{ref}",
        f"https://api.github.com/repos/{owner}/{repo}/commits/{ref}",
    ):
        try:
            resp = await _fetch(url)
            status = resp.status if sys.platform == "emscripten" else resp.code
            if status == 200:
                return True
        except Exception:
            continue
    return False


async def _get_ocp_requirements_from_pypi(build123d_version):
    response = await _fetch(f"https://pypi.org/pypi/build123d/{build123d_version}/json")

    if sys.platform == "emscripten":
        data = await response.json()
    else:
        import json

        data = json.load(response)

    requires_dist = data["info"].get("requires_dist", [])
    mock_versions, ocp_specifiers = _parse_dep_requirements(requires_dist)

    if sys.platform == "emscripten":
        for req in requires_dist:
            req = req.replace("(", "").replace(")", "")
            if req.startswith("ipython"):
                ipy = await (await _fetch("https://pypi.org/pypi/ipython/json")).json()
                for ir in ipy["info"].get("requires_dist", []):
                    ir = ir.replace("(", "").replace(")", "")
                    if ir.startswith("psutil"):
                        suffix = ir[len("psutil") :].lstrip()
                        if suffix and suffix[0] in (">", "<", "=", "~", "!", "("):
                            v = _select_mock_version(suffix)
                            if v and (
                                "psutil" not in mock_versions
                                or v > mock_versions["psutil"]
                            ):
                                mock_versions["psutil"] = v
                        break

        for pkg_name, version in mock_versions.items():
            micropip.add_mock_package(pkg_name, version)

    return mock_versions, ocp_specifiers


async def _get_ocp_requirements_from_pyproject(build123d_ref):
    ref_type = "heads" if build123d_ref == "dev" else "tags"

    if sys.platform == "emscripten":
        content = await (
            await _fetch(
                f"https://raw.githubusercontent.com/gumyr/build123d/refs/{ref_type}/{build123d_ref}/pyproject.toml"
            )
        ).text()
    else:
        import urllib.request

        content = (
            urllib.request.urlopen(
                f"https://raw.githubusercontent.com/gumyr/build123d/refs/{ref_type}/{build123d_ref}/pyproject.toml"
            )
            .read()
            .decode()
        )

    import tomllib

    deps = tomllib.loads(content).get("project", {}).get("dependencies", [])

    mock_versions, ocp_specifiers = _parse_dep_requirements(deps)

    if sys.platform == "emscripten":
        for pkg_name, version in mock_versions.items():
            micropip.add_mock_package(pkg_name, version)

    return mock_versions, ocp_specifiers


async def _install_ocp_wasm_wheels(ocp_specifiers):
    if sys.platform == "emscripten":
        lib3mf_spec = ocp_specifiers.get("lib3mf", "")
        await micropip.install(f"lib3mf-OCP.wasm{lib3mf_spec}")
        _version = importlib.metadata.version("lib3mf-OCP.wasm")
        micropip.add_mock_package(
            "py-lib3mf", _version, modules={"py_lib3mf": "from lib3mf import *"}
        )

        ocp_novtk_spec = ocp_specifiers.get("cadquery-ocp-novtk", "")
        await micropip.install(f"cadquery-ocp-novtk-OCP.wasm{ocp_novtk_spec}")

        await micropip.install("sqlite3")
    else:
        import asyncio
        import subprocess

        lib3mf_spec = ocp_specifiers.get("lib3mf", "")
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pip",
            "install",
            f"lib3mf-OCP.wasm{lib3mf_spec}",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise Exception(f"Failed to install lib3mf-OCP.wasm:\n{stderr.decode()}")

        ocp_novtk_spec = ocp_specifiers.get("cadquery-ocp-novtk", "")
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pip",
            "install",
            f"cadquery-ocp-novtk-OCP.wasm{ocp_novtk_spec}",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise Exception(
                f"Failed to install cadquery-ocp-novtk-OCP.wasm:\n{stderr.decode()}"
            )


async def _remove_mocks(mock_versions):
    if sys.platform == "emscripten":
        for pkg_name in mock_versions:
            micropip.remove_mock_package(pkg_name)


def _extract_and_patch_github(sources_bytes, ref):
    version = "0.0.0+dev" if ref == "dev" else ref.strip("v")
    _tmpdir = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(file=io.BytesIO(sources_bytes), mode="r") as zipf:
        zipf.extractall(path=_tmpdir.name)

    _extracted_dir = os.path.join(_tmpdir.name, os.listdir(_tmpdir.name)[0])
    _sources_folder = os.path.join(_extracted_dir, "src")
    sys.path.insert(0, _sources_folder)

    pyproject_path = os.path.join(_extracted_dir, "pyproject.toml")
    with open(pyproject_path, "r") as f:
        pyproject_content = f.read()
    pyproject_content = re.sub(
        r'dynamic = \["version"]', 'version = "' + version + '"', pyproject_content
    )
    pyproject_content = re.sub(r'"setuptools_scm.*?",', "", pyproject_content)
    pyproject_content = re.sub(
        r"\[tool\.setuptools.*]\n([^\[].*?\n)*", "", pyproject_content
    )
    with open(pyproject_path, "w") as f:
        f.write(pyproject_content)

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

    import tomllib

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

    return _tmpdir, _extracted_dir, _dependencies, version


async def _fetch_bytes(url):
    """Fetch URL and return bytes, following redirects and handling non-error codes."""
    max_redirects = 5
    for _ in range(max_redirects):
        response = await _fetch(url)
        status = response.status if sys.platform == "emscripten" else response.code
        # Handle HTTP redirects (3xx)
        if 300 <= status < 400:
            if sys.platform == "emscripten":
                location = response.headers.get("Location")
            else:
                location = response.getheader("Location")
            if not location:
                raise RuntimeError(f"Redirect with no Location header for {url}")
            url = location
            continue
        # Accept 200-299 as success
        if 200 <= status < 300:
            if sys.platform == "emscripten":
                return await response.bytes()
            else:
                return response.read()
        # Otherwise, error
        raise RuntimeError(f"Failed to fetch {url}: HTTP {status}")
    raise RuntimeError(f"Too many redirects while fetching {url}")


async def _install_build123d_from_github(ref):
    sources_bytes = None
    for url in (
        f"https://github.com/gumyr/build123d/archive/refs/heads/{ref}.zip",
        f"https://github.com/gumyr/build123d/archive/refs/tags/{ref}.zip",
        f"https://github.com/gumyr/build123d/archive/{ref}.zip",
    ):
        try:
            sources_bytes = await _fetch_bytes(url)
            break
        except Exception:
            continue
    if sources_bytes is None:
        raise RuntimeError(f"Could not fetch GitHub ref: {ref}")

    _tmpdir, _extracted_dir, _dependencies, _version = _extract_and_patch_github(
        sources_bytes, ref
    )

    if sys.platform == "emscripten":
        for dep in _dependencies:
            dep = dep.strip()
            if not dep:
                continue
            if (
                dep.startswith("lib3mf")
                or dep.startswith("cadquery-ocp")
                or dep.strip() == "mypy"
            ):
                continue
            print(f"Installing dependency: {dep}")
            await micropip.install(dep, reinstall=True)
    else:
        import asyncio
        import subprocess

        for dep in _dependencies:
            dep = dep.strip()
            if not dep:
                continue
            if (
                dep.startswith("lib3mf")
                or dep.startswith("cadquery-ocp")
                or dep.strip() == "mypy"
            ):
                continue
            print(f"Installing dependency: {dep}")
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pip",
                "install",
                dep,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise Exception(f"Failed to install package {dep}:\n{stderr.decode()}")

    return _tmpdir, _extracted_dir


async def bootstrap(build123d_version_arg="stable"):
    """Bootstrap build123d for testing. Works in both native and Pyodide environments.

    Args:
        build123d_version_arg: "stable" (latest PyPI), "vX.Y.Z" (PyPI version), or GitHub ref (branch/tag/commit)

    Returns:
        (tmpdir, extracted_dir): tmpdir for cleanup, extracted_dir for use (None if installed from PyPI)
    """
    if build123d_version_arg == "stable":
        response = await _fetch("https://pypi.org/pypi/build123d/json")
        if sys.platform == "emscripten":
            data = await response.json()
        else:
            import json

            data = json.load(response)
        build123d_version_arg = "v" + data["info"]["version"]

    tmpdir = None
    extracted_dir = None
    mock_versions = None

    if await _is_github_ref("gumyr", "build123d", build123d_version_arg):
        mock_versions, ocp_specifiers = await _get_ocp_requirements_from_pyproject(
            build123d_version_arg
        )
        await _install_ocp_wasm_wheels(ocp_specifiers)
        tmpdir, extracted_dir = await _install_build123d_from_github(
            build123d_version_arg
        )
    else:
        mock_versions, ocp_specifiers = await _get_ocp_requirements_from_pypi(
            build123d_version_arg
        )
        await _install_ocp_wasm_wheels(ocp_specifiers)
        if sys.platform == "emscripten":
            await micropip.install("build123d==" + build123d_version_arg)
        else:
            import asyncio
            import subprocess

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pip",
                "install",
                "build123d==" + build123d_version_arg,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise Exception(f"Failed to install build123d:\n{stderr.decode()}")

    if mock_versions:
        await _remove_mocks(mock_versions)

    return tmpdir, extracted_dir
