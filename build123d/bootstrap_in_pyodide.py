import importlib.metadata

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


async def _is_github_ref(owner, repo, ref):
    from pyodide.http import pyfetch

    for url in (
        f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{ref}",
        f"https://api.github.com/repos/{owner}/{repo}/git/ref/tags/{ref}",
        f"https://api.github.com/repos/{owner}/{repo}/commits/{ref}",
    ):
        resp = await pyfetch(url)
        if resp.status == 200:
            return True
    return False


async def _get_ocp_requirements_from_pypi(build123d_version):
    from pyodide.http import pyfetch

    response = await pyfetch(f"https://pypi.org/pypi/build123d/{build123d_version}/json")
    data = await response.json()
    requires_dist = data["info"].get("requires_dist", [])

    mock_versions, ocp_specifiers = _parse_dep_requirements(requires_dist)

    for req in requires_dist:
        req = req.replace("(", "").replace(")", "")
        if req.startswith("ipython"):
            ipy = await (await pyfetch("https://pypi.org/pypi/ipython/json")).json()
            for ir in ipy["info"].get("requires_dist", []):
                ir = ir.replace("(", "").replace(")", "")
                if ir.startswith("psutil"):
                    suffix = ir[len("psutil"):].lstrip()
                    if suffix and suffix[0] in (">", "<", "=", "~", "!", "("):
                        v = _select_mock_version(suffix)
                        if v and ("psutil" not in mock_versions or v > mock_versions["psutil"]):
                            mock_versions["psutil"] = v
                    break

    for pkg_name, version in mock_versions.items():
        micropip.add_mock_package(pkg_name, version)

    return mock_versions, ocp_specifiers


async def _get_ocp_requirements_from_pyproject(build123d_ref):
    from pyodide.http import pyfetch

    ref_type = "heads" if build123d_ref == "dev" else "tags"
    content = await (await pyfetch(
        f"https://raw.githubusercontent.com/gumyr/build123d/refs/{ref_type}/{build123d_ref}/pyproject.toml"
    )).text()

    import tomllib
    deps = tomllib.loads(content).get("project", {}).get("dependencies", [])

    mock_versions, ocp_specifiers = _parse_dep_requirements(deps)

    for pkg_name, version in mock_versions.items():
        micropip.add_mock_package(pkg_name, version)

    return mock_versions, ocp_specifiers


async def _install_ocp_wasm_wheels(ocp_specifiers):
    lib3mf_spec = ocp_specifiers.get("lib3mf", "")
    await micropip.install(f"lib3mf-OCP.wasm{lib3mf_spec}")
    _version = importlib.metadata.version("lib3mf-OCP.wasm")
    micropip.add_mock_package("py-lib3mf", _version, modules={"py_lib3mf": "from lib3mf import *"})

    ocp_novtk_spec = ocp_specifiers.get("cadquery-ocp-novtk", "")
    await micropip.install(f"cadquery-ocp-novtk-OCP.wasm{ocp_novtk_spec}")

    await micropip.install("sqlite3")


async def _remove_mocks(mock_versions):
    for pkg_name in mock_versions:
        micropip.remove_mock_package(pkg_name)


async def _install_build123d_from_github(ref):
    from pyodide.http import pyfetch
    import zipfile, io, tempfile, re, tomllib, os, sys

    sources_bytes = None
    for url in (
        f"https://github.com/gumyr/build123d/archive/refs/heads/{ref}.zip",
        f"https://github.com/gumyr/build123d/archive/refs/tags/{ref}.zip",
        f"https://github.com/gumyr/build123d/archive/zipball/{ref}",
    ):
        try:
            response = await pyfetch(
                "https://little-hill-4bc4.yeicor-cloudflare.workers.dev/?url=" + url
            )
            sources_bytes = await response.bytes()
            break
        except Exception:
            continue
    if sources_bytes is None:
        raise RuntimeError(f"Could not fetch GitHub ref: {ref}")

    version = '0.0.0+dev' if ref == "dev" else ref.strip("v")
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

    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)
    _dependencies = pyproject_data.get("project", {}).get("dependencies", [])
    if os.getenv("_install_build123d_from_github_also_optional", "") != "":
        _dependencies += pyproject_data.get("project", {}).get("optional-dependencies", {}).get("development", [])
        _dependencies += pyproject_data.get("project", {}).get("optional-dependencies", {}).get("benchmark", [])

    for dep in _dependencies:
        dep = dep.strip()
        if not dep:
            continue
        if dep.startswith("lib3mf") or dep.startswith("cadquery-ocp") or dep.strip() == "mypy":
            continue
        print(f"Installing dependency: {dep}")
        await micropip.install(dep, reinstall=True)

    return _tmpdir, _extracted_dir


async def bootstrap(build123d_version_arg="stable"):
    if build123d_version_arg == "stable":
        from pyodide.http import pyfetch
        stable_version = (await (await pyfetch("https://pypi.org/pypi/build123d/json")).json())["info"]["version"]
        build123d_version_arg = "v" + stable_version

    tmpdir = None
    extracted_dir = None
    mock_versions = None

    if await _is_github_ref("gumyr", "build123d", build123d_version_arg):
        mock_versions, ocp_specifiers = await _get_ocp_requirements_from_pyproject(build123d_version_arg)
        await _install_ocp_wasm_wheels(ocp_specifiers)
        tmpdir, extracted_dir = await _install_build123d_from_github(build123d_version_arg)
    else:
        mock_versions, ocp_specifiers = await _get_ocp_requirements_from_pypi(build123d_version_arg)
        await _install_ocp_wasm_wheels(ocp_specifiers)
        await micropip.install("build123d==" + build123d_version_arg)

    if mock_versions:
        await _remove_mocks(mock_versions)

    return tmpdir, extracted_dir
