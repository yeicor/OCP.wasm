import importlib.metadata
import micropip

async def bootstrap():
    # build123d depends on ipython which depends on psutil and is unsupported on pyodide, so mock it
    micropip.add_mock_package("psutil", "7.2.2")

    # lib3mf-OCP.wasm provides the `lib3mf` Python module (wasm port)
    await micropip.install("lib3mf-OCP.wasm")
    _version = importlib.metadata.version("lib3mf-OCP.wasm")
    micropip.add_mock_package("lib3mf", _version)
    # ONLY for build123d versions <0.10.0, we need to redirect the import of `py_lib3mf` to our ported `lib3mf` package.
    micropip.add_mock_package("py-lib3mf", _version, modules={"py_lib3mf": "from lib3mf import *"})

    # cadquery-ocp-novtk-OCP.wasm provides the OCP Python module (wasm port)
    await micropip.install("cadquery-ocp-novtk-OCP.wasm")
    _version = importlib.metadata.version("cadquery-ocp-novtk-OCP.wasm")
    micropip.add_mock_package("cadquery-ocp-novtk", _version)
    micropip.add_mock_package("ocp", _version)

    # Required stdlib package, missing on Pyodide by default due to size
    await micropip.install("sqlite3")

    # Ready to actually install build123d and all dependencies
    await micropip.install("build123d")

    # You can now include your own build123d script, as `import build123d` will work.
