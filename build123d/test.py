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
    import zipfile, io, tempfile, os, re, tomllib

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

    _tmpdir = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(file=io.BytesIO(sources_bytes), mode="r") as zipf:
        zipf.extractall(path=_tmpdir.name)

    _extracted_dir = os.path.join(_tmpdir.name, os.listdir(_tmpdir.name)[0])
    _sources_folder = os.path.join(_extracted_dir, "src")
    sys.path.insert(0, _sources_folder)

    pyproject_path = os.path.join(_extracted_dir, "pyproject.toml")
    with open(pyproject_path, "r") as f:
        pyproject_content = f.read()
    pyproject_content = re.sub(r'dynamic = \["version"]', 'version = "' + ref + '"', pyproject_content)
    pyproject_content = re.sub(r'"setuptools_scm.*?",', "", pyproject_content)
    pyproject_content = re.sub(r'\[tool\.setuptools.*]\n([^\[].*?\n)*', "", pyproject_content)
    with open(pyproject_path, "w") as f:
        f.write(pyproject_content)

    init_path = os.path.join(_sources_folder, "build123d", "__init__.py")
    with open(init_path, "r") as f:
        init_content = f.read()
    init_content = re.sub(r"from \.version import version as __version__", f"__version__ = '{ref}'", init_content)
    with open(init_path, "w") as f:
        f.write(init_content)

    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)
    _dependencies = pyproject_data.get("project", {}).get("dependencies", [])
    _dependencies += pyproject_data.get("project", {}).get("optional-dependencies", {}).get("development", [])
    _dependencies += pyproject_data.get("project", {}).get("optional-dependencies", {}).get("benchmark", [])

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
    import os, json, urllib.request

    branch = os.environ.get("BUILD123D_BRANCH", "dev")
    if branch == "stable":
        with urllib.request.urlopen("https://pypi.org/pypi/build123d/json") as r:
            branch = "v" + json.load(r)["info"]["version"]

    if sys.platform == "emscripten":
        from bootstrap_in_pyodide import bootstrap
        from pyodide.ffi import run_sync
        import micropip

        tmpdir, extracted_dir = await bootstrap(branch)
        os.environ["_install_build123d_from_github_also_optional"] = "true"

        def _new_urlretrieve(url, filename=None, reporthook=None, data=None):
            if url.startswith("https://") and filename is not None and not reporthook and not data:
                from pyodide.http import pyfetch
                bs = run_sync(pyfetch(url).then(lambda r: r.bytes()))
                with open(filename, "wb") as f:
                    f.write(bs)
                return filename, {}
            else:
                return _old_urlretrieve(url, filename, reporthook, data)

        import urllib.request
        _old_urlretrieve = urllib.request.urlretrieve
        urllib.request.urlretrieve = _new_urlretrieve

        await micropip.install("font-fetcher")
        from font_fetcher.ocp import install_ocp_font_hook
        install_ocp_font_hook()

        def _new_subprocess_run(cmd, *args, **kwargs):
            if cmd[0] == sys.executable and cmd[1] == '-c':
                import io, contextlib, subprocess
                code = cmd[2]
                stdout = io.StringIO()
                stderr = io.StringIO()
                exit_code = 0
                oldwd = os.getcwd()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    try:
                        os.chdir(kwargs.get('cwd', oldwd))
                        exec(code.replace(').read()', ', "rb").read().decode("utf-8")'), {})
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
