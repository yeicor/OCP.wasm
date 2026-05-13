import importlib.metadata
import io
import os
import re
import sys
import tempfile
import zipfile

import micropip


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
                suffix = req[len(pkg_name):].lstrip()
                if not suffix or suffix[0] not in (">", "<", "=", "~", "!", "("):
                    continue
                version = _select_mock_version(suffix)
                if version:
                    if pkg_name not in mock_versions or version > mock_versions[pkg_name]:
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


def _is_github_ref(version_str):
    return version_str == "dev" or version_str.startswith("v")


async def _get_ocp_requirements_from_pypi(build123d_version):
    from pyodide.http import pyfetch

    url = f"https://pypi.org/pypi/build123d/{build123d_version}/json"
    response = await pyfetch(url)
    data = await response.json()
    requires_dist = data["info"].get("requires_dist", [])

    mock_versions, ocp_specifiers = _parse_dep_requirements(requires_dist)

    for req in requires_dist:
        req = req.replace("(", "").replace(")", "")
        if req.startswith("ipython"):
            resp = await pyfetch("https://pypi.org/pypi/ipython/json")
            ipy = await resp.json()
            for ir in ipy["info"].get("requires_dist", []):
                ir = ir.replace("(", "").replace(")", "")
                if ir.startswith("psutil"):
                    suffix = ir[len("psutil"):].lstrip()
                    if suffix and suffix[0] in (">", "<", "=", "~", "!", "("):
                        v = _select_mock_version(suffix)
                        if v:
                            if "psutil" not in mock_versions or v > mock_versions["psutil"]:
                                mock_versions["psutil"] = v
                    break

    for pkg_name, version in mock_versions.items():
        micropip.add_mock_package(pkg_name, version)

    return mock_versions, ocp_specifiers


async def _get_ocp_requirements_from_pyproject(build123d_ref):
    from pyodide.http import pyfetch

    ref_type = "heads" if build123d_ref == "dev" else "tags"
    url = f"https://raw.githubusercontent.com/gumyr/build123d/refs/{ref_type}/{build123d_ref}/pyproject.toml"

    response = await pyfetch(url)
    content = await response.text()

    import tomllib
    pyproject_data = tomllib.loads(content)
    deps = pyproject_data.get("project", {}).get("dependencies", [])

    mock_versions, ocp_specifiers = _parse_dep_requirements(deps)

    for pkg_name, version in mock_versions.items():
        micropip.add_mock_package(pkg_name, version)

    return mock_versions, ocp_specifiers


async def _install_ocp_wheels(ocp_specifiers):
    lib3mf_spec = ocp_specifiers.get("lib3mf", "")
    await micropip.install(f"lib3mf-OCP.wasm{lib3mf_spec}")
    _version = importlib.metadata.version("lib3mf-OCP.wasm")
    micropip.add_mock_package("py-lib3mf", _version, modules={"py_lib3mf": "from lib3mf import *"})

    ocp_novtk_spec = ocp_specifiers.get("cadquery-ocp-novtk", "")
    await micropip.install(f"cadquery-ocp-novtk-OCP.wasm{ocp_novtk_spec}")
    await micropip.install("sqlite3")


async def _remove_mocks(mock_versions):
    for pkg_name, _version in mock_versions.items():
        micropip.remove_mock_package(pkg_name)


async def _install_build123d_from_github(tag_or_branch):
    from pyodide.http import pyfetch

    ref_type = "heads" if tag_or_branch == "dev" else "tags"
    version = '0.0.0+dev' if tag_or_branch == "dev" else tag_or_branch.strip("v")

    sources_url = f"https://github.com/gumyr/build123d/archive/refs/{ref_type}/{tag_or_branch}.zip"
    if sys.platform == "emscripten":
        sources_url = "https://little-hill-4bc4.yeicor-cloudflare.workers.dev/?url=" + sources_url

    print(f"Downloading build123d {tag_or_branch} from: {sources_url}")
    response = await pyfetch(sources_url)
    sources_bytes = await response.bytes()

    _tmpdir = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(file=io.BytesIO(sources_bytes), mode="r") as zipf:
        zipf.extractall(path=_tmpdir.name)

    _extracted_dir = os.path.join(_tmpdir.name, os.listdir(_tmpdir.name)[0])
    _sources_folder = os.path.join(_extracted_dir, "src")
    sys.path.insert(0, _sources_folder)

    pyproject_path = os.path.join(_extracted_dir, "pyproject.toml")
    with open(pyproject_path, "r") as f:
        pyproject_content = f.read()
    pyproject_content = re.sub(r'dynamic = \["version"]', 'version = "' + version + '"', pyproject_content)
    pyproject_content = re.sub(r'"setuptools_scm.*?",', "", pyproject_content)
    pyproject_content = re.sub(r'\[tool\.setuptools.*]\n([^\[].*?\n)*', "", pyproject_content)
    with open(pyproject_path, "w") as f:
        f.write(pyproject_content)

    init_path = os.path.join(_sources_folder, "build123d", "__init__.py")
    with open(init_path, "r") as f:
        init_content = f.read()
    init_content = re.sub(r"from \.version import version as __version__", f"__version__ = '{version}'", init_content)
    with open(init_path, "w") as f:
        f.write(init_content)

    import tomllib
    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)
        _dependencies = pyproject_data.get("project", {}).get("dependencies", [])
        _dependencies += pyproject_data.get("project", {}).get("optional-dependencies", {}).get("development", [])
        _dependencies += pyproject_data.get("project", {}).get("optional-dependencies", {}).get("benchmark", [])

    for dep in _dependencies:
        dep = dep.strip()
        if not dep:
            continue
        pkg_name = dep.split("[")[0].split(">")[0].split("<")[0].split("=")[0].split("~")[0].split("!")[0].strip()
        if pkg_name in ("lib3mf", "cadquery-ocp", "cadquery-ocp-novtk", "mypy"):
            continue
        print(f"Installing dependency: {dep}")
        await micropip.install(dep, reinstall=True)

    import build123d
    assert build123d.__version__ == version, "Version mismatch: expected " + version + ", got " + build123d.__version__

    return _tmpdir, _extracted_dir


async def bootstrap(build123d_version_arg="stable"):
    if build123d_version_arg == "stable":
        from pyodide.http import pyfetch
        response = await pyfetch("https://pypi.org/pypi/build123d/json")
        data = await response.json()
        stable_version = data["info"]["version"]
        build123d_version_arg = "v" + stable_version

    tmpdir = None
    extracted_dir = None
    mock_versions = None

    if _is_github_ref(build123d_version_arg):
        ref = build123d_version_arg
        pypi_version = None if ref == "dev" else ref.strip("v")
        if pypi_version:
            mock_versions, ocp_specifiers = await _get_ocp_requirements_from_pypi(pypi_version)
        else:
            mock_versions, ocp_specifiers = await _get_ocp_requirements_from_pyproject(ref)
        await _install_ocp_wheels(ocp_specifiers)
        tmpdir, extracted_dir = await _install_build123d_from_github(ref)
    else:
        mock_versions, ocp_specifiers = await _get_ocp_requirements_from_pypi(build123d_version_arg)
        await _install_ocp_wheels(ocp_specifiers)
        await micropip.install("build123d==" + build123d_version_arg)

    if mock_versions:
        await _remove_mocks(mock_versions)

    return tmpdir, extracted_dir
