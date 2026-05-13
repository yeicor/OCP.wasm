import sys


async def _download_and_patch(tag_or_branch, common_fetch, install_package):
    import zipfile, io, tempfile, os, re

    ref_type = "heads" if tag_or_branch == "dev" else "tags"
    sources_url = "https://github.com/gumyr/build123d/archive/refs/" + ref_type + "/" + tag_or_branch + ".zip"
    version = '0.0.0+dev' if tag_or_branch == "dev" else tag_or_branch.strip("v")
    print("Running tests for build123d " + version + " from: " + sources_url)
    sources_bytes = await common_fetch(sources_url)

    _tmpdir = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(file=io.BytesIO(sources_bytes), mode="r") as zipf:
        zipf.extractall(path=_tmpdir.name)

    _extracted_dir = os.path.join(_tmpdir.name, os.listdir(_tmpdir.name)[0])
    _sources_folder = os.path.join(_extracted_dir, "src")
    sys.path.insert(0, _sources_folder)

    pyproject_path = os.path.join(_extracted_dir, "pyproject.toml")
    with open(pyproject_path, "r") as f:
        pyproject_content = f.read()
    pyproject_content = re.sub(r'dynamic = \["version"]', 'version = "' + version + '"', pyproject_content)
    pyproject_content = re.sub(r'"setuptools_scm.*?",', "", pyproject_content)
    pyproject_content = re.sub(r'\[tool\.setuptools.*]\n([^\[].*?\n)*', "", pyproject_content)
    with open(pyproject_path, "w") as f:
        f.write(pyproject_content)

    init_path = os.path.join(_sources_folder, "build123d", "__init__.py")
    with open(init_path, "r") as f:
        init_content = f.read()
    init_content = re.sub(r"from \.version import version as __version__", "__version__ = '" + version + "'",
                          init_content)
    with open(init_path, "w") as f:
        f.write(init_content)

    import tomllib
    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)
        _dependencies = pyproject_data.get("project", {}).get("dependencies", [])
        _dependencies += pyproject_data.get("project", {}).get("optional-dependencies", {}).get("development", [])
        _dependencies += pyproject_data.get("project", {}).get("optional-dependencies", {}).get("benchmark", [])
        if sys.platform == "emscripten":
            _dependencies += ["sqlite3"]
            _dependencies = [d for d in _dependencies if d.strip() != "mypy"]
            _dependencies = [d for d in _dependencies if not d.startswith("lib3mf") and not d.startswith("cadquery-ocp")]

    for dep in _dependencies:
        dep = dep.strip()
        if not dep:
            continue
        print("Installing dependency: " + dep)
        await install_package(dep)

    import build123d
    assert build123d.__version__ == version, "Version mismatch: expected " + version + ", got " + build123d.__version__

    return _extracted_dir, _tmpdir


async def main():
    import argparse, os

    default_branch = os.environ.get("BUILD123D_BRANCH", "dev")

    if default_branch == "stable":
        with open(os.path.join(os.path.dirname(__file__), "requirements-stable.txt"), "r") as f:
            default_branch = f.readline().strip()
            if default_branch.startswith("build123d=="):
                default_branch = "v" + default_branch.split("==")[1]

    parser = argparse.ArgumentParser(description="Download and test build123d package.")
    parser.add_argument("branch", nargs='?', default=default_branch,
                        help="The tag/branch of build123d to test (default: dev).")
    args = parser.parse_args()

    from crossplatformtricks import bootstrap, common_fetch, install_package
    if sys.platform == "emscripten":
        tmpdir, extracted_dir = await bootstrap(args.branch)
    else:
        extracted_dir, tmpdir = await _download_and_patch(args.branch, common_fetch, install_package)

    old_cwd = os.getcwd()
    try:
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
