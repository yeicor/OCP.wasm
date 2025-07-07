def download_and_patch_build123d(tag_or_branch: str):
    # Clone the sources from the specified branch
    sources_url = f"https://github.com/gumyr/build123d/archive/refs/{"heads" if tag_or_branch == "dev" else "tags"}/{tag_or_branch}.zip"
    version = '0.0.0+dev' if args.branch == "dev" else args.branch.strip("v")
    print(f"Running tests for build123d {version} from: {sources_url}")
    sources_bytes = common_fetch(sources_url)

    # Extract it to a temporary directory
    _tmpdir = tempfile.TemporaryDirectory()
    # noinspection PyTypeChecker
    with zipfile.ZipFile(file=io.BytesIO(sources_bytes), mode="r") as zipf:
        zipf.extractall(path=_tmpdir.name)

    # Locate the extracted directory (assuming the zip contains a single top-level directory)
    _extracted_dir = os.path.join(_tmpdir.name, os.listdir(_tmpdir.name)[0])
    _sources_folder = os.path.join(_extracted_dir, "src")
    sys.path.insert(0, _sources_folder)

    # setuptools_scm does not work because this is not a git repository, so we remove all mentions from pyproject.toml
    pyproject_path = os.path.join(_extracted_dir, "pyproject.toml")
    assert os.path.isfile(pyproject_path), "pyproject.toml not found in the extracted sources"
    with open(pyproject_path, "r") as f:
        pyproject_content = f.read()
        pyproject_content = re.sub(r'dynamic = \["version"]', 'version = "' + version + '"', pyproject_content)
        pyproject_content = re.sub(r'"setuptools_scm.*?",', "", pyproject_content)
        pyproject_content = re.sub(r'\[tool\.setuptools.*]\n([^\[].*?\n)*', "", pyproject_content)
        print("Patched pyproject.toml to remove setuptools_scm references:\n", pyproject_content)
    with open(pyproject_path, "w") as f:
        f.write(pyproject_content)

    # Patch the __init__.py to set the __version__ to the branch name
    init_path = os.path.join(_sources_folder, "build123d", "__init__.py")
    assert os.path.isfile(init_path), "src/build123d/__init__.py not found in the extracted sources"
    with open(init_path, "r") as f:
        init_content = f.read()
        init_content = re.sub(r"from \.version import version as __version__", f"__version__ = '{version}'",
                              init_content)
        print("Patched build123d/__init__.py to set __version__ to:", version)
    with open(init_path, "w") as f:
        f.write(init_content)

    # Find all dependencies from pyproject.toml and install them
    import tomllib
    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)
        _dependencies = pyproject_data.get("project", {}).get("dependencies", [])
        _dependencies += pyproject_data.get("project", {}).get("optional-dependencies", {}).get("development", [])
        _dependencies += pyproject_data.get("project", {}).get("optional-dependencies", {}).get("benchmark", [])
        if sys.platform == "emscripten": _dependencies += ["sqlite3"]  # sqlite3 is not included by default in Pyodide
    for dep in _dependencies:
        dep = dep.strip()
        if dep:
            print(f"Installing dependency: {dep}")
            install_package(dep)

    # Sanity check: import build123d results in a matching version to these patched sources
    import build123d
    assert build123d.__version__ == version, "Version mismatch: expected " + version + ", got " + build123d.__version__

    return _extracted_dir, _tmpdir


if __name__ == "__main__":
    import argparse, zipfile, tempfile, io, unittest, os, re
    from crossplatformtricks import *

    # Basic CLI argument parsing
    parser = argparse.ArgumentParser(description="Download and test build123d package.")
    parser.add_argument("branch", nargs='?', default="dev", help="The branch of build123d to test (default: dev).")
    args = parser.parse_args()

    old_cwd = os.getcwd()
    tmpdir = None
    try:
        extracted_dir, tmpdir = download_and_patch_build123d(args.branch)

        # Set the working directory so relative paths work
        tests_path = os.path.join(extracted_dir, "tests")
        if not os.path.isdir(tests_path):
            raise FileNotFoundError("No 'tests/' directory found in the sdist")
        os.chdir(extracted_dir)

        # Discover all tests
        loader = unittest.TestLoader()
        suite = unittest.TestSuite(loader.discover("tests"))

        # Run all tests while printing basic progress
        result = unittest.TextTestRunner().run(suite)

        # Fail on any test failure
        if result.wasSuccessful():
            print("All tests passed successfully!")
        else:
            print("Some tests failed. Check the output above for details.")
            sys.exit(1)
    finally:
        # Restore the original working directory and clean up the temporary directory
        os.chdir(old_cwd)
        if tmpdir is not None: tmpdir.cleanup()
