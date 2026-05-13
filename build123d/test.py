import sys


async def _native_fetch(url):
    import urllib.request
    with urllib.request.urlopen(url) as response:
        return response.read()


async def _native_install(package_name):
    import subprocess, asyncio
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-m', 'pip', 'install', package_name,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise Exception(f"Failed to install package {package_name}:\n{stderr.decode()}")


async def _native_bootstrap(ref):
    sources_bytes = None
    for url in (
        f"https://github.com/gumyr/build123d/archive/refs/heads/{ref}.zip",
        f"https://github.com/gumyr/build123d/archive/refs/tags/{ref}.zip",
        f"https://github.com/gumyr/build123d/archive/zipball/{ref}",
    ):
        try:
            sources_bytes = await _native_fetch(url)
            break
        except Exception:
            continue
    if sources_bytes is None:
        raise RuntimeError(f"Could not fetch GitHub ref: {ref}")

    from bootstrap_in_pyodide import _extract_and_patch_github

    _tmpdir, _extracted_dir, _dependencies, version = _extract_and_patch_github(sources_bytes, ref)

    for dep in _dependencies:
        dep = dep.strip()
        if not dep:
            continue
        print(f"Installing dependency: {dep}")
        await _native_install(dep)

    import build123d
    assert build123d.__version__ == version, f"Version mismatch: expected {version}, got {build123d.__version__}"

    return _extracted_dir, _tmpdir


async def main():
    import os, sys, json, urllib.request

    branch = os.environ.get("BUILD123D_BRANCH") or (sys.argv[1] if len(sys.argv) > 1 else "dev")
    if branch == "stable":
        with urllib.request.urlopen("https://pypi.org/pypi/build123d/json") as r:
            branch = "v" + json.load(r)["info"]["version"]

    os.environ["_install_build123d_from_github_also_optional"] = "true"

    if sys.platform == "emscripten":
        from bootstrap_in_pyodide import bootstrap
        from pyodide.ffi import run_sync
        import micropip

        tmpdir, extracted_dir = await bootstrap(branch)

        def _new_urlretrieve(url, filename=None, reporthook=None, data=None):
            if url.startswith("https://") and filename is not None and not reporthook and not data:
                from pyodide.http import pyfetch
                response = run_sync(pyfetch(url))
                bs = run_sync(response.bytes())
                with open(filename, "wb") as f:
                    f.write(bs)
                return filename, {}
            else:
                return _old_urlretrieve(url, filename, reporthook, data)

        import urllib.request
        _old_urlretrieve = urllib.request.urlretrieve
        urllib.request.urlretrieve = _new_urlretrieve

        import os as _os
        import build123d

        await micropip.install("font-fetcher")
        from font_fetcher.ocp import install_ocp_font_hook
        from OCP.Font import Font_FontMgr, Font_SystemFont, Font_FA_Regular
        from OCP.TCollection import TCollection_AsciiString
        _real_font_mgr = Font_FontMgr.GetInstance_s()
        install_ocp_font_hook()
        font_path = _os.path.join(
            extracted_dir, "src", "build123d", "data", "fonts",
            "reliefsingleline", "ReliefSingleLineCAD-Regular.ttf",
        )
        _font_t = Font_SystemFont(TCollection_AsciiString("singleline"))
        _font_t.SetFontPath(Font_FA_Regular, TCollection_AsciiString(font_path))
        _real_font_mgr.RegisterFont(_font_t, True)

        def _new_subprocess_run(cmd, *args, **kwargs):
            if cmd[0] == sys.executable and cmd[1] == '-c':
                import io, contextlib, re, subprocess
                code = cmd[2]

                def _inline_file(m):
                    path_repr = m.group(1)
                    path = path_repr[2:-1] if path_repr.startswith("r'") else path_repr[1:-1]
                    with open(path, encoding="utf-8") as f:
                        return f"exec({repr(f.read())})"

                code = re.sub(r"exec\(open\(((?:r)?'[^']+')[^)]*\)\.read\(\)\)", _inline_file, code)
                stdout = io.StringIO()
                stderr = io.StringIO()
                exit_code = 0
                oldwd = os.getcwd()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    try:
                        os.chdir(kwargs.get('cwd', oldwd))
                        exec(code, {})
                    except Exception as e:
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
    else:
        extracted_dir, tmpdir = await _native_bootstrap(branch)

    old_cwd = os.getcwd()
    try:
        if extracted_dir is not None:
            os.chdir(extracted_dir)

        import pytest
        exit_code = pytest.main([
            "-vvv",
            "-s",
            "--setup-show",
            "--tb=long",
            "--ignore=tests/test_direct_api/test_jupyter.py",
            "--ignore=tests/test_direct_api/test_vtk_poly_data.py",
            "-k=not (test_make_surface_error_checking or test_edge_wrapper_radius or test_make_surface_patch or ((TestAxis or TestLocation or TestPlane) and test_set) or test_tan3_2)",
        ])

        if exit_code == 0:
            print("All tests passed successfully!")
            return True
        else:
            print("Some tests failed. Check the output above for details.")
            sys.exit(1)
    finally:
        os.chdir(old_cwd)
        if tmpdir is not None:
            tmpdir.cleanup()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
