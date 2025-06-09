# OCP wasm

[OCP](https://github.com/CadQuery/OCP) builds for WebAssembly using Pyodide.


## Usage example

Go to [the Pyodide REPL](https://pyodide.org/en/latest/console.html).

Run the following code:

```py
import micropip
await micropip.install([
    "https://yeicor.github.io/OCP-wasm/cibw-wheels-wasm-Release/cadquery_ocp-7.8.1.2-cp313-cp313-pyodide_2025_0_wasm32.whl",
    "build123d", "sqlite3"])

from build123d import *

L, w, t, b, h, n = 60.0, 18.0, 9.0, 0.9, 90.0, 6.0

with BuildPart() as ex29:
    with BuildSketch(Plane.XY.offset(-b)) as ex29_ow_sk:
        with BuildLine() as ex29_ow_ln:
            l1 = Line((0, 0), (0, w / 2))
            l2 = ThreePointArc(l1 @ 1, (L / 2.0, w / 2.0 + t), (L, w / 2.0))
            l3 = Line(l2 @ 1, ((l2 @ 1).X, 0, 0))
            _ = mirror(ex29_ow_ln.line)
        _ = make_face()
    _ = extrude(amount=h + b)
    _ = fillet(ex29.edges(), radius=w / 6)
    with BuildSketch(ex29.faces().sort_by(Axis.Z)[-1]):
        _ = Circle(t)
    _ = extrude(amount=n)
    necktopf = ex29.faces().sort_by(Axis.Z)[-1]
    _ = offset(ex29.solids()[0], amount=-b, openings=necktopf)

print("Volume:", ex29.part.volume)
```
