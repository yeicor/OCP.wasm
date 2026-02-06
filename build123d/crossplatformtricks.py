import os
import sys

if sys.platform == 'emscripten':
    from bootstrap_in_pyodide import bootstrap as _bootstrap

    async def bootstrap():
        ocp_index = os.environ.get("OCP_WASM_INDEX_URL", "https://yeicor.github.io/OCP.wasm")
        print(f"Bootstrapping build123d with index {ocp_index}...")
        await _bootstrap(ocp_index)

        # Now bootstrap a few optional extra hacks to make all build123d tests pass in pyodide

        # XXX: Patch urllib.request.urlretrieve to use pyodide's pyfetch as it is too low level for pyodide (and it is not critical for build123d but required for test_importers.ImportSTEP)
        def _new_urlretrieve(url, filename=None, reporthook=None, data=None):
            # Try to avoid breaking other uses of urlretrieve (which are probably unsupported anyway)
            if url.startswith("https://") and filename is not None and not reporthook and not data:
                # print("XXX: Using patched urllib.request.urlretrieve to use pyodide's pyfetch for URL:", url)
                from pyodide.ffi import run_sync
                bs = run_sync(common_fetch(url))  # Download the file to cache it
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
        

    async def common_fetch(url: str) -> bytes:
        from pyodide.http import pyfetch
        response = await pyfetch(url)
        return await response.bytes()


    async def install_package(package_name: str):
        import micropip
        await micropip.install(package_name, reinstall=True)


else:


    async def bootstrap():
        pass # Nothing to do for non-pyodide platforms
        

    async def common_fetch(url: str) -> bytes:
        import urllib.request
        with urllib.request.urlopen(url) as response:
            return response.read()


    async def install_package(package_name: str):
        import subprocess
        import sys
        # Install the package using pip
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', 'pip', 'install', package_name,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise Exception(f"Failed to install package {package_name}:\n{stderr.decode()}")
