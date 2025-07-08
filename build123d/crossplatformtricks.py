import sys

if sys.platform == 'emscripten':
    print("Bootstrapping build123d...")
    import bootstrap_in_pyodide  # noqa: F401


    def common_fetch(url: str) -> bytes:
        from pyodide.http import pyfetch
        import asyncio
        # noinspection PyUnresolvedReferences
        loop = asyncio.get_event_loop()
        response = loop.run_until_complete(pyfetch(url))
        return loop.run_until_complete(response.bytes())


    # XXX: Patch urllib.request.urlretrieve to use pyodide's pyfetch as it is too low level for pyodide (and it is not critical for build123d but required for test_importers.ImportSTEP)
    import urllib.request

    _old_urlretrieve = urllib.request.urlretrieve


    def _new_urlretrieve(url, filename=None, reporthook=None, data=None):
        # Try to avoid breaking other uses of urlretrieve (which are probably unsupported anyway)
        if url.startswith("https://") and filename is not None and not reporthook and not data:
            #print("XXX: Using patched urllib.request.urlretrieve to use pyodide's pyfetch for URL:", url)
            bs = common_fetch(url)  # Download the file to cache it
            with open(filename, "wb") as f:
                f.write(bs)
            return filename, {}  # Return the filename and a dummy response object
        else:
            return _old_urlretrieve(url, filename, reporthook, data)


    urllib.request.urlretrieve = _new_urlretrieve


    # XXX: Download and install any font so that the tests can run
    def install_font_to_ocp(font_url, font_name=None):
        from pyodide.http import pyfetch
        from OCP.Font import Font_FontMgr, Font_SystemFont, Font_FA_Regular
        from OCP.TCollection import TCollection_AsciiString
        import os, asyncio

        font_name = font_name if font_name is not None else font_url.split("/")[-1]

        # Choose a "system-like" font directory
        font_path = os.path.join("/tmp", font_name)
        os.makedirs(os.path.dirname(font_path), exist_ok=True)

        # Download the font using pyfetch
        loop = asyncio.get_event_loop()
        response = loop.run_until_complete(pyfetch(font_url))
        font_data = loop.run_until_complete(response.bytes())

        # Save it to the system-like folder
        with open(font_path, "wb") as f:
            f.write(font_data)

        mgr = Font_FontMgr.GetInstance_s()
        font_t = Font_SystemFont(TCollection_AsciiString(font_path))
        font_t.SetFontPath(Font_FA_Regular, TCollection_AsciiString(font_path))
        assert mgr.RegisterFont(font_t, False)
        print(f"✅ Font installed at: {font_path}")
        return font_path


    # Make sure there is at least one font installed, so that the tests can run
    install_font_to_ocp("https://raw.githubusercontent.com/kavin808/arial.ttf/refs/heads/master/arial.ttf")


    def install_package(package_name: str):
        import micropip, asyncio
        # noinspection PyUnresolvedReferences
        loop = asyncio.get_event_loop()

        # Install the package using micropip
        loop.run_until_complete(micropip.install(package_name))


else:

    def common_fetch(url: str) -> bytes:
        import urllib.request
        with urllib.request.urlopen(url) as response:
            return response.read()


    def install_package(package_name: str):
        import subprocess
        import sys
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package_name])
        except subprocess.CalledProcessError as e:
            print(f"Failed to install package {package_name}: {e}")
            sys.exit(1)
