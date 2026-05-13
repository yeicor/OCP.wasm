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
        ocp_specifiers["cadquery-ocp-novtk"] = ocp_specifiers.get("cadquery-ocp", "")
    if "cadquery-ocp-novtk" in mock_versions and "cadquery-ocp" not in mock_versions:
        mock_versions["cadquery-ocp"] = mock_versions["cadquery-ocp-novtk"]
        ocp_specifiers["cadquery-ocp"] = ocp_specifiers.get("cadquery-ocp-novtk", "")

    for pkg_name, version in mock_versions.items():
        micropip.add_mock_package(pkg_name, version)

    return data["info"]["version"] if build123d_version == "stable" else build123d_version, mock_versions, ocp_specifiers


async def bootstrap(build123d_version_arg="stable"):
    # Get version requirements from build123d metadata first (also sets up mocks)
    build123d_version, mock_versions, ocp_specifiers = await _mock_from_build123d_metadata(build123d_version_arg)

    # Install OCP.wasm wheels with version pinning based on build123d's requirements
    lib3mf_spec = ocp_specifiers.get("lib3mf", "")
    await micropip.install(f"lib3mf-OCP.wasm{lib3mf_spec}")
    # py-lib3mf mock is only needed for build123d < 0.10.0
    _version = importlib.metadata.version("lib3mf-OCP.wasm")
    micropip.add_mock_package("py-lib3mf", _version, modules={"py_lib3mf": "from lib3mf import *"})

    ocp_novtk_spec = ocp_specifiers.get("cadquery-ocp-novtk", "")
    await micropip.install(f"cadquery-ocp-novtk-OCP.wasm{ocp_novtk_spec}")
    await micropip.install("sqlite3") # This is not included by default on pyodide, so install it too

    # Install the requested build123d version (mocks from _mock_from_build123d_metadata satisfy dependency resolution)
    await micropip.install(f"build123d=={build123d_version}")

    # Remove the mocks now that build123d is installed, so imports like
    # "from lib3mf import Lib3MF" resolve to the real OCP.wasm packages.
    for pkg_name, _version in mock_versions.items():
        micropip.remove_mock_package(pkg_name)
