# Utility to bootstrap this testing environment onto the Pyodide REPL. You just need to paste the following line:
#
# import micropip; from pyodide.http import pyfetch; exec(await (await pyfetch("https://raw.githubusercontent.com/yeicor/OCP.wasm/master/build123d/test_bootstrap_browser.py")).text())
#
# You can also run `import os; os.environ["BUILD123D_BRANCH"] = "dev"` before the above line to test a specific version of build123d.

import asyncio
import io
import os
import sys
import tempfile
import zipfile

# noinspection PyUnresolvedReferences
from pyodide.http import pyfetch

# First, download a snapshot of the repository.
print("Downloading the latest OCP.wasm sources...")
loop = asyncio.get_event_loop()
response = loop.run_until_complete(pyfetch("https://api.codetabs.com/v1/proxy?quest=https://github.com/yeicor/OCP.wasm/archive/refs/heads/master.zip"))
sources_zip = loop.run_until_complete(response.bytes())

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
from test import main

main()
