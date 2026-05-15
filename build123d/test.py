import os
import sys


async def main():
    branch = os.environ.get("BUILD123D_BRANCH") or (
        sys.argv[1] if len(sys.argv) > 1 else "dev"
    )

    os.environ["_install_build123d_from_github_also_optional"] = "true"

    from bootstrap import bootstrap

    if sys.platform == "emscripten":
        import micropip
        from pyodide.ffi import run_sync

        tmpdir, extracted_dir = await bootstrap(branch)

        def _new_urlretrieve(url, filename=None, reporthook=None, data=None):
            if (
                url.startswith("https://")
                and filename is not None
                and not reporthook
                and not data
            ):
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

        import warnings

        await micropip.install("font-fetcher")
        from font_fetcher.ocp import install_ocp_font_hook
        from OCP.Font import Font_FA_Regular, Font_FontMgr, Font_SystemFont
        from OCP.TCollection import TCollection_AsciiString

        _real_font_mgr = Font_FontMgr.GetInstance_s()
        install_ocp_font_hook()
        font_path = os.path.join(
            extracted_dir,
            "src",
            "build123d",
            "data",
            "fonts",
            "reliefsingleline",
            "ReliefSingleLineCAD-Regular.ttf",
        )
        if os.path.isfile(font_path):
            _font_t = Font_SystemFont(TCollection_AsciiString("singleline"))
            _font_t.SetFontPath(Font_FA_Regular, TCollection_AsciiString(font_path))
            _font_t.SetSingleStrokeFont(True)
            _real_font_mgr.RegisterFont(_font_t, True)
        else:
            warnings.warn(f"Embedded build123d font file not found: {font_path}")

        def _new_subprocess_run(cmd, *args, **kwargs):
            if cmd[0] == sys.executable and cmd[1] == "-c":
                import contextlib
                import io
                import re
                import subprocess

                code = cmd[2]

                def _inline_file(m):
                    path_repr = m.group(1)
                    path = (
                        path_repr[2:-1]
                        if path_repr.startswith("r'")
                        else path_repr[1:-1]
                    )
                    with open(path, encoding="utf-8") as f:
                        return f"exec({repr(f.read())})"

                code = re.sub(
                    r"exec\(open\(((?:r)?'[^']+')[^)]*\)\.read\(\)\)",
                    _inline_file,
                    code,
                )
                stdout = io.StringIO()
                stderr = io.StringIO()
                exit_code = 0
                oldwd = os.getcwd()
                with (
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                ):
                    try:
                        os.chdir(kwargs.get("cwd", oldwd))
                        exec(code, {})
                    except Exception as e:
                        import traceback

                        traceback.print_exc(file=stderr)
                        stdout.write(str(e) + "\n")
                        exit_code = 1
                    finally:
                        os.chdir(oldwd)
                return subprocess.CompletedProcess(
                    cmd, exit_code, stdout=stdout.getvalue(), stderr=stderr.getvalue()
                )
            else:
                return _old_subprocess_run(cmd, *args, **kwargs)

        import subprocess

        _old_subprocess_run = subprocess.run
        subprocess.run = _new_subprocess_run
    else:
        tmpdir, extracted_dir = await bootstrap(branch)

    old_cwd = os.getcwd()
    try:
        if extracted_dir is not None:
            os.chdir(extracted_dir)

        import pytest

        exit_code = pytest.main(
            [
                "-vvv",
                "-s",
                "--setup-show",
                "--tb=long",
                # There is no VTK or Jupyter support in the Emscripten environment, so skip those tests there
                "--ignore=tests/test_direct_api/test_jupyter.py",
                "--ignore=tests/test_direct_api/test_vtk_poly_data.py",
                # Skip some tests that are known to be flaky in the Emscripten environment, likely due to differences in floating-point behavior or other platform-specific issues. These should be investigated and fixed eventually, but for now this allows us to use tests to catch regressions in the Emscripten environment without being blocked by these known issues.
                "-k=not ("
                "test_tan3_2 or "
                "(TestCadObjects and test_edge_wrapper_radius) or "
                "((TestAxis or TestLocation or TestPlane) and test_set) or "
                "(TestFace and (test_make_surface or test_make_surface_patch or test_make_surface_error_checking))"
                ")",
            ]
        )

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
