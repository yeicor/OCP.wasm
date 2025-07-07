# OCP.wasm — CAD Modeling in the Browser with WebAssembly & Pyodide

OCP.wasm brings the full power of [build123d](https://build123d.readthedocs.io/) —the intuitive Pythonic 3D CAD library—
directly into your browser.

No installs. No setup. 100% private browser-native code-first CAD.

## Quick Start

Go to [the Pyodide REPL](https://pyodide.org/en/stable/console.html) and
run [this code](build123d/bootstrap_in_pyodide.py).
Then, run your build123d script as usual.

For extra tricks required for passing 100% of the build123d tests, see [this code](build123d/crossplatformtricks.py).

Performance and support may vary across browsers.

## Projects using OCP.wasm

- [build123dWebAssmGenDemo](https://github.com/Radther/build123dWebAssmGenDemo): A web-based 3D model generator that
  creates parametric models using Python and WebAssembly ([demo](https://radther.github.io/build123dWebAssmGenDemo/)).
