import os
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
    def _new_urlretrieve(url, filename=None, reporthook=None, data=None):
        # Try to avoid breaking other uses of urlretrieve (which are probably unsupported anyway)
        if url.startswith("https://") and filename is not None and not reporthook and not data:
            # print("XXX: Using patched urllib.request.urlretrieve to use pyodide's pyfetch for URL:", url)
            bs = common_fetch(url)  # Download the file to cache it
            with open(filename, "wb") as f:
                f.write(bs)
            return filename, {}  # Return the filename and a dummy response object
        else:
            return _old_urlretrieve(url, filename, reporthook, data)


    import urllib.request

    _old_urlretrieve = urllib.request.urlretrieve
    urllib.request.urlretrieve = _new_urlretrieve

    # XXX: Download and install any font so that the tests can run
    import asyncio, micropip

    asyncio.run(micropip.install(["font-fetcher"]))
    from font_fetcher.ocp import install_ocp_font_hook

    install_ocp_font_hook()


    # XXX: Patch subprocess to use exec with empty globals if we are just running python code... (less isolation, but more compatibility)
    def _new_subprocess_run(cmd, *args, **kwargs):
        if cmd[0] == sys.executable and cmd[1] == '-c':  # If we are running Python code directly (too specific)
            import io
            import contextlib
            import subprocess
            code = cmd[2]
            stdout = io.StringIO()
            stderr = io.StringIO()
            exit_code = 0
            oldwd = os.getcwd()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    os.chdir(kwargs.get('cwd', oldwd))  # Change to the specified working directory if provided
                    exec(code.replace(').read()', ', "rb").read().decode("utf-8")'), {})
                except Exception as e:
                    # Print exception's stack trace to stderr
                    import traceback
                    traceback.print_exc(file=stderr)
                    stdout.write(str(e) + "\n")
                    exit_code = 1
                finally:
                    os.chdir(oldwd)
            return subprocess.CompletedProcess(cmd, exit_code, stdout=stdout.getvalue(), stderr=stderr.getvalue())
        else:
            return _old_subprocess_run(cmd, *args, **kwargs)


    import subprocess

    _old_subprocess_run = subprocess.run
    subprocess.run = _new_subprocess_run


    def install_package(package_name: str):
        # Install the package using micropip
        asyncio.run(micropip.install(package_name))


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
