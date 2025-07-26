# OCP.wasm — CAD Modeling in the Browser with WebAssembly & Pyodide

OCP.wasm brings the full power of [build123d](https://build123d.readthedocs.io/) —the intuitive Pythonic 3D CAD library—
directly into your browser.

No installs. No setup. 100% private browser-native code-first CAD.

This project ports the low-level dependencies required for build123d to run in a browser.
For a fully featured frontend, check out [Yet Another CAD Viewer](https://github.com/yeicor-3d/yet-another-cad-viewer)
or other [projects using OCP.wasm](#projects-using-ocpwasm) below.

*Performance and support may vary across browsers.*

## Quick Start

Go to [the Pyodide REPL](https://pyodide.org/en/stable/examples/console_webworker.html) and
run [this code](build123d/bootstrap_in_pyodide.py).
Then, run your build123d script as usual.

(Optional) For extra tricks required for passing 100% of the build123d tests,
see [this code](build123d/crossplatformtricks.py).

(Optional) To run all the tests in your (chrome-only for now) browser,
use [the Pyodide REPL](https://pyodide.org/en/stable/examples/console_webworker.html)
and follow the intructions at the top of [the test bootstrapping script](build123d/test_bootstrap_browser.py).

Check out the [Pyodide docs](https://pyodide.org/en/stable/) to integrate OCP.wasm into your own
applications. Or look at the [projects using OCP.wasm](#projects-using-ocpwasm) below for inspiration.

## Projects using OCP.wasm

- [Yet Another CAD Viewer](https://github.com/yeicor-3d/yet-another-cad-viewer):  A CAD viewer capable of displaying OCP
  models (CadQuery/Build123d) in a web
  browser. ([🌐 demo](https://yeicor-3d.github.io/yet-another-cad-viewer/#pg_code_url=https://raw.githubusercontent.com/gumyr/build123d/refs/heads/dev/examples/toy_truck.py)).
- [build123dWebAssmGenDemo](https://github.com/Radther/build123dWebAssmGenDemo): A web-based 3D model generator that
  creates parametric models using Python and WebAssembly ([🌐 demo](https://radther.github.io/build123dWebAssmGenDemo/)).
- [build123d-sandbox](https://github.com/jojain/build123d-sandbox/): A minimal webapp to expose the Python CAD library
  build123d in the browser using a compiled wasm OCP backend ([🌐 demo](https://jojain.github.io/build123d-sandbox/)).
