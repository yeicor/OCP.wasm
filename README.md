# OCP.wasm — CAD Modeling in the Browser with WebAssembly & Pyodide

OCP.wasm brings the full power of [build123d](https://build123d.readthedocs.io/) —the intuitive Pythonic 3D CAD library—
directly into your browser.

No installs. No setup. No servers. 100% private browser-native code-first CAD.


## WIP: Quick Start

Go to [the Pyodide REPL](https://pyodide.org/en/latest/console.html) and run the following code:

```py
import micropip
await micropip.install([
    "https://yeicor.github.io/OCP-wasm/cadquery-ocp-wasm-Release/cadquery_ocp-7.8.1.2-cp313-cp313-pyodide_2025_0_wasm32.whl",
    "build123d", "sqlite3"])
from build123d import Box

# Replace the following code with your own build123d script.
b = Box(1, 2, 3)
assert b.volume == 6.0, "Box volume should be 6.0"
```
