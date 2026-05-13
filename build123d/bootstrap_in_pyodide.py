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


async def _mock_from_build123d_metadata(build123d_version="stable"):
    from pyodide.http import pyfetch

    url = "https://pypi.org/pypi/build123d/json"
    if build123d_version != "stable":
        url = f"https://pypi.org/pypi/build123d/{build123d_version}/json"

    response = await pyfetch(url)
    data = await response.json()
    requires_dist = data["info"].get("requires_dist", [])

    mock_versions = {}

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
                break

        if req.startswith("ipython"): # Always assume latest, as build123d uses wide valid range
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

    if "cadquery-ocp" in mock_versions and "cadquery-ocp-novtk" not in mock_versions:
        mock_versions["cadquery-ocp-novtk"] = mock_versions["cadquery-ocp"]
    if "cadquery-ocp-novtk" in mock_versions and "cadquery-ocp" not in mock_versions:
        mock_versions["cadquery-ocp"] = mock_versions["cadquery-ocp-novtk"]

    for pkg_name, version in mock_versions.items():
        micropip.add_mock_package(pkg_name, version)

    return data["info"]["version"] if build123d_version == "stable" else build123d_version, mock_versions


def _add_pywrap_s_aliases():
    import OCP

    mods_to_process = [OCP]
    seen = set()
    while mods_to_process:
        mod = mods_to_process.pop()
        if id(mod) in seen:
            continue
        seen.add(id(mod))
        for name in dir(mod):
            if name.startswith("_"):
                continue
            try:
                attr = getattr(mod, name)
            except Exception:
                continue
            s_name = name + "_s"
            if hasattr(mod, s_name):
                continue
            try:
                setattr(mod, s_name, attr)
            except Exception:
                pass
            if isinstance(attr, type(mod)):
                mods_to_process.append(attr)


async def bootstrap(build123d_version_arg="stable"):
    # Install our custom webassembly-compatible dependencies of build123d, and mock the original ones
    await micropip.install("lib3mf-OCP.wasm")
    _version = importlib.metadata.version("lib3mf-OCP.wasm")
    micropip.add_mock_package("py-lib3mf", _version, modules={"py_lib3mf": "from lib3mf import *"})
    await micropip.install("cadquery-ocp-novtk-OCP.wasm")
    _add_pywrap_s_aliases()
    build123d_version, mock_versions = await _mock_from_build123d_metadata(build123d_version_arg)
    await micropip.install("sqlite3") # This is not included by default on pyodide, so install it too

    # Install the requested build123d version (mocks satisfy dependency resolution)
    await micropip.install(f"build123d=={build123d_version}")

    # Remove the mocks now that build123d is installed, so imports like
    # "from lib3mf import Lib3MF" resolve to the real OCP.wasm packages.
    for pkg_name, _version in mock_versions.items():
        micropip.remove_mock_package(_pkg)
