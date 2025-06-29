# This script downloads a Python package from PyPI, extracts it, and runs its unittests.

import io
import os
import sys
import tempfile
import unittest
import zipfile
from unittest import TextTestRunner

if sys.platform == 'emscripten':
    import micropip, asyncio

    # Install build123d and its dependencies at runtime, unlike other platforms
    micropip.add_mock_package("py-lib3mf", "2.4.1", modules={
        "py_lib3mf": '''import micropip; import asyncio; asyncio.run(micropip.install("lib3mf")); from lib3mf import *'''})  # Only required for build123d<0.10.0


    def common_fetch(url: str) -> bytes:
        from pyodide.http import pyfetch
        # noinspection PyUnresolvedReferences
        loop = asyncio.get_event_loop()
        response = loop.run_until_complete(pyfetch(url))
        return loop.run_until_complete(response.bytes())


    # XXX: Download and install any font so that the tests can run
    async def install_font_to_system(font_url, font_name):
        from pyodide.http import pyfetch
        from OCP.Font import Font_FontMgr, Font_SystemFont, Font_FA_Regular
        from OCP.TCollection import TCollection_AsciiString
        # Choose a "system-like" font directory
        font_path = os.path.join("/tmp", font_name)
        os.makedirs(os.path.dirname(font_path), exist_ok=True)

        # Download the font using pyfetch
        response = await pyfetch(font_url)
        font_data = await response.bytes()

        # Save it to the system-like folder
        with open(font_path, "wb") as f:
            f.write(font_data)

        mgr = Font_FontMgr.GetInstance_s()
        font_t = Font_SystemFont(TCollection_AsciiString(font_path))
        font_t.SetFontPath(Font_FA_Regular, TCollection_AsciiString(font_path))
        assert mgr.RegisterFont(font_t, False)
        print(f"✅ Font installed at: {font_path}")
        return font_path


    asyncio.get_event_loop().run_until_complete(install_font_to_system(
        "https://raw.githubusercontent.com/google/fonts/refs/heads/main/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf",
        "Roboto.ttf"))  # Fake to avoid warnings

    # XXX: Workaround for lib3mf crash due to WASM_BIGINT emscripten bug? FIXME: Try force-disabling WASM_BIGINT instead?
    import lib3mf

    old_init = lib3mf.Base.__init__


    def new_init(self, handle, wrapper):
        wrapper.checkError = lambda self, error: print("Ignoring buggy checkError call")  # type: ignore[method-assign]
        # Also write stubs for all methods with 4 arguments to avoid errors
        for method_name in dir(wrapper.lib):
            if method_name.startswith("lib3mf_") and '_get' in method_name:
                method = getattr(wrapper.lib, method_name)
                if callable(method):
                    print("Ignoring buggy method: ", method_name)
                    setattr(wrapper.lib, method_name,
                            lambda *args: print("Ignoring buggy call to", method_name))  # type: ignore[method-assign]
        return old_init(self, handle, wrapper)


    lib3mf.Base.__init__ = new_init
else:

    def common_fetch(url: str) -> bytes:
        import urllib.request
        with urllib.request.urlopen(url) as response:
            return response.read()


# TODO: Add alias in FontMgr from Arial to first font if no Arial font found (to avoid warnings)
# FIXME: assert mgr.AddFontAlias(TCollection_AsciiString("Arial"), TCollection_AsciiString("Roboto"))


def download_and_test(sdist_url="https://github.com/gumyr/build123d/archive/refs/heads/dev.zip", test_subdir="tests"):
    # Download the .zip file
    sdist_data = common_fetch(sdist_url)

    # Extract it to a temporary directory
    tmpdir = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(file=io.BytesIO(sdist_data), mode="r") as zipf:
        zipf.extractall(path=tmpdir.name)

    # Locate the extracted directory
    extracted_dir = os.path.join(tmpdir.name,
                                 os.listdir(tmpdir.name)[0])  # Assuming the zip contains a single top-level directory
    sys.path.insert(0, extracted_dir)

    # Run unittests in the "tests" folder
    tests_path = os.path.join(extracted_dir, test_subdir)
    if not os.path.isdir(tests_path):
        raise FileNotFoundError("No 'tests/' directory found in the sdist")

    # 🔧 Set the working directory so relative paths work
    old_cwd = os.getcwd()
    os.chdir(extracted_dir)

    try:
        # Discover all tests
        loader = unittest.TestLoader()
        suite = unittest.TestSuite(loader.discover("tests"))
        result = TextTestRunner().run(suite)
        return result
    finally:
        # Restore the original working directory
        os.chdir(old_cwd)


if __name__ == "__main__":
    import build123d

    sources_url = "https://github.com/gumyr/build123d/archive/refs/heads/dev.zip"
    if "dev" not in build123d.__version__:
        sources_url = f"https://github.com/gumyr/build123d/archive/refs/tags/v{build123d.__version__}.zip"

    print("Running tests for build123d from:", sources_url)
    download_and_test(sources_url)
