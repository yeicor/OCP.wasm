import asyncio, micropip

# If using the Pyodide JS API, you need to `loadPackage("micropip")` first.

# Prioritize the OCP.wasm package repository so that wasm-specific packages are preferred.
micropip.set_index_urls(["https://yeicor.github.io/OCP.wasm", "https://pypi.org/simple"])

# For build123d versions <0.10.0, we need to redirect the import of `py_lib3mf` to our ported `lib3mf` package.
micropip.add_mock_package("py-lib3mf", "2.4.1", modules={
    "py_lib3mf": '''import micropip, asyncio; asyncio.run(micropip.install("lib3mf")); from lib3mf import *'''})

# Install the required packages (if stack switching is not available, use `await` instead of `asyncio.run`, same above!).
asyncio.run(micropip.install(["build123d", "sqlite3"]))

# You can now include your own build123d script, as `import build123d` will work.
