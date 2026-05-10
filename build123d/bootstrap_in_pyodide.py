import micropip, asyncio, os, warnings, re

async def bootstrap(ocp_index = "https://yeicor.github.io/OCP.wasm"):
    # If using the Pyodide JS API, you need to `loadPackage("micropip")` first.

    # Prioritize the OCP.wasm package repository so that wasm-specific packages are preferred.
    micropip.set_index_urls([ocp_index, "https://pypi.org/simple"])

    # ONLY for build123d versions <0.10.0, we need to redirect the import of `py_lib3mf` to our ported `lib3mf` package.
    await micropip.install("lib3mf")
    micropip.add_mock_package("py-lib3mf", "2.4.1", modules={"py_lib3mf": '''from lib3mf import *'''})

    # Missing on Pyodide by default
    await micropip.install("sqlite3")

    # Install the required packages, warning on dependencies that are unsupported on WASM.
    async def graceful_install(requirements, **kwargs):
        await micropip.install("packaging")
        from packaging.requirements import Requirement
        kwargs = dict(kwargs)
        kwargs["keep_going"] = True
        try:
            await micropip.install(requirements, **kwargs)
        except ValueError as e:
            matches = re.findall(r"'([^']+)'", str(e))

            if not matches:
                raise

            for req_str in matches:
                req = Requirement(req_str)
                pkg_name = req.name

                mock_version = "999.9.9"

                for spec in req.specifier:
                    if spec.operator in ("==", ">=", "~="):
                        mock_version = spec.version
                        break

                warnings.warn(
                    f"Mocking {pkg_name} with version {mock_version}"
                )

                micropip.add_mock_package(pkg_name, mock_version)

            kwargs.pop("keep_going", None)
            await micropip.install(requirements, **kwargs)

    await graceful_install("build123d")

    # You can now include your own build123d script, as `import build123d` will work.
