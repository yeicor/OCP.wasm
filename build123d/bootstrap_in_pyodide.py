import importlib.metadata
import micropip


def _parse_first_compatible_version(spec_str):
    for part in spec_str.split(","):
        part = part.strip()
        for op in (">=", "~=", "=="):
            if part.startswith(op):
                return part[len(op):].strip()
    return None


async def _mock_from_build123d_metadata():
    try:
        from pyodide.http import pyfetch
        response = await pyfetch("https://pypi.org/pypi/build123d/json")
        data = await response.json()
        for req in data["info"].get("requires_dist", []):
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
    except Exception:
        import warnings
        warnings.warn("Failed to fetch build123d metadata from PyPI; mocks may be missing")


async def bootstrap():
    micropip.add_mock_package("psutil", "7.2.2")

    await micropip.install("lib3mf-OCP.wasm")
    _version = importlib.metadata.version("lib3mf-OCP.wasm")
    micropip.add_mock_package("py-lib3mf", _version, modules={"py_lib3mf": "from lib3mf import *"})

    await micropip.install("cadquery-ocp-novtk-OCP.wasm")

    await _mock_from_build123d_metadata()

    await micropip.install("sqlite3")

    await micropip.install("build123d")
