import micropip, asyncio, os, warnings, re

async def bootstrap(ocp_index = "https://yeicor.github.io/OCP.wasm"):
    # If using the Pyodide JS API, you need to `loadPackage("micropip")` first.

    # Prioritize the OCP.wasm package repository so that wasm-specific packages are preferred.
    micropip.set_index_urls([ocp_index, "https://pypi.org/simple"])

    # build123d depends on ipython which depends on psutil and is unsupported on pyodide, so mock it
    micropip.add_mock_package("psutil", "7.2.2")

    # ONLY for build123d versions <0.10.0, we need to redirect the import of `py_lib3mf` to our ported `lib3mf` package.
    await micropip.install("lib3mf")
    micropip.add_mock_package("py-lib3mf", "2.4.1", modules={"py_lib3mf": '''from lib3mf import *'''})

    # Required stdlib package, missing on Pyodide by default due to size
    await micropip.install("sqlite3")

    # Ready to actually install build123d and all dependencies
    await micropip.install("build123d")

    # You can now include your own build123d script, as `import build123d` will work.
