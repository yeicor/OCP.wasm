# Utility to bootstrap this testing environment onto the Pyodide REPL. You just need to paste the following line:
#
# import os; os.environ["OCP_WASM_BRANCH"] = "master"; os.environ["BUILD123D_BRANCH"] = "dev"; import micropip; from pyodide.http import pyfetch; exec(await (await pyfetch("https://raw.githubusercontent.com/yeicor/OCP.wasm/"+os.environ["OCP_WASM_BRANCH"]+"/build123d/test_bootstrap_browser.py")).text())

import io
import os
import sys
import tempfile
import urllib.parse  # Assume CORS error and try proxy instead
import zipfile

from pyodide.ffi import run_sync  # type: ignore
from pyodide.http import pyfetch  # type: ignore

# First, download a snapshot of the repository.
print("Downloading the latest OCP.wasm sources...")
OCP_WASM_BRANCH = os.environ.get("OCP_WASM_BRANCH", "master")
response = run_sync(
    pyfetch(
        "https://little-hill-4bc4.yeicor-cloudflare.workers.dev/?url="
        + urllib.parse.quote_plus(
            "https://github.com/yeicor/OCP.wasm/archive/refs/heads/"
            + OCP_WASM_BRANCH
            + ".zip"
        )
    )
)
sources_zip = run_sync(response.bytes())

# Then, extract it to a temporary directory.
print("Extracting the sources to a temporary directory...")
_tmpdir = tempfile.TemporaryDirectory()
# noinspection PyTypeChecker
with zipfile.ZipFile(file=io.BytesIO(sources_zip), mode="r") as zipf:
    zipf.extractall(path=_tmpdir.name)

# Import the main function from the test module and run it.
print("Running the test script...")
_tests_dir = os.path.join(_tmpdir.name, os.listdir(_tmpdir.name)[0], "build123d")
sys.path.insert(0, _tests_dir)

# Ruff E402: Module level import not at top of file - intentionally ignored here
from test import main  # noqa: E402

run_sync(main())
