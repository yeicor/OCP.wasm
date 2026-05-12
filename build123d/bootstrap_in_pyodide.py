import importlib.metadata
import micropip


def _parse_first_compatible_version(spec_str):
    for part in spec_str.split(","):
        part = part.strip()
        for op in (">=", "~=", "==", ">"):
            if part.startswith(op):
                return part[len(op):].strip()
    return None


async def _mock_from_build123d_metadata(build123d_version="stable"):
    from pyodide.http import pyfetch

    url = "https://pypi.org/pypi/build123d/json"
    if build123d_version != "stable":
        url = f"https://pypi.org/pypi/build123d/{build123d_version}/json"

    response = await pyfetch(url)
    data = await response.json()
    requires_dist = data["info"].get("requires_dist", [])

    for req in requires_dist:
        req = req.replace("(", "").replace(")", "")
        for pkg_name in ("cadquery-ocp-novtk", "cadquery-ocp", "lib3mf"):
            if req.startswith(pkg_name):
                suffix = req[len(pkg_name):].lstrip()
                if not suffix or suffix[0] not in (">", "<", "=", "~", "!", "("):
                    continue
                version = _parse_first_compatible_version(suffix)
                if version:
                    micropip.add_mock_package(pkg_name, version)
                break

        if req.startswith("ipython"): # Always assume latest, as build123d uses wide valid range
            resp = await pyfetch("https://pypi.org/pypi/ipython/json")
            ipy = await resp.json()
            for ir in ipy["info"].get("requires_dist", []):
                ir = ir.replace("(", "").replace(")", "")
                if ir.startswith("psutil"):
                    suffix = ir[len("psutil"):].lstrip()
                    if suffix and suffix[0] in (">", "<", "=", "~", "!", "("):
                        v = _parse_first_compatible_version(suffix)
                        if v:
                            micropip.add_mock_package("psutil", v)
                    break

    return data["info"]["version"] if build123d_version == "stable" else build123d_version


async def bootstrap(build123d_version_arg="stable"):
    # Install our custom webassembly-compatible dependencies of build123d, and mock the original ones
    await micropip.install("lib3mf-OCP.wasm")
    _version = importlib.metadata.version("lib3mf-OCP.wasm")
    micropip.add_mock_package("py-lib3mf", _version, modules={"py_lib3mf": "from lib3mf import *"})
    await micropip.install("cadquery-ocp-novtk-OCP.wasm")
    build123d_version = await _mock_from_build123d_metadata(build123d_version_arg)
    await micropip.install("sqlite3") # This is not included by default on pyodide, so install it too

    # Install the requested build123d version
    await micropip.install(f"build123d=={build123d_version}")
