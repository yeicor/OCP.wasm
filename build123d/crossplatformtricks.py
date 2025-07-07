import sys

if sys.platform == 'emscripten':
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
            print("XXX: Using patched urllib.request.urlretrieve to use pyodide's pyfetch for URL:", url)
            bs = common_fetch(url)  # Download the file to cache it
            with open(filename, "wb") as f:
                f.write(bs)
            return filename, {}  # Return the filename and a dummy response object
        else:
            return _old_urlretrieve(url, filename, reporthook, data)


    urllib.request.urlretrieve = _new_urlretrieve


    def install_package(package_name: str):
        import micropip
        import asyncio
        # noinspection PyUnresolvedReferences
        loop = asyncio.get_event_loop()
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
