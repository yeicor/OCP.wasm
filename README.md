# OCP.wasm — CAD Modeling in the Browser with WebAssembly & Pyodide

OCP.wasm brings the full power of [build123d](https://build123d.readthedocs.io/) —the intuitive Pythonic 3D CAD library—
directly into your browser.

No installs. No setup. No servers. 100% private browser-native code-first CAD.


## WIP: Quick Start

Go to [the Pyodide REPL](https://pyodide.org/en/latest/console.html) and run the following code:

```py
import micropip
micropip.set_index_urls("https://yeicor.github.io/OCP.wasm#ignored={package_name}")
micropip.add_mock_package("py_lib3mf", "2.4.1", modules={"py_lib3mf": '''from lib3mf import *'''}) # Only required for build123d<0.10.0
await micropip.install("build123d")

# Replace the following lines with your own build123d script.
from build123d import Box
b = Box(1, 2, 3)
assert b.volume == 6.0, "Box volume should be 6.0"
```
