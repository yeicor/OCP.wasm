import micropip, asyncio, os, warnings

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
        from packaging.requirement import Requirement
        kwargs["keep_going"] = True
        try:
            await micropip.install(requirements, **kwargs)
        except ValueError as e:
            error_msg = str(e)
            match = re.search(r"wheel for '(.*?)'\.", error_msg)
            if not match:
                raise e
                
            raw_failed_specs = match.group(1)
            
            # Micropip often joins conflicting constraints into a single string like 'pkg==1,==2'
            # We split by commas and treat each as a potential requirement part
            for part in re.split(r"', '|,", raw_failed_specs):
                # Use 'packaging' to parse the specifier correctly
                req = Requirement(part.strip().strip("'"))
                pkg_name = req.name
                
                # Attempt to find a 'valid' version from the specifier
                # If pkg==1.2.3 is requested, we use 1.2.3. 
                # If no specific version is found, 999.9.9 is a safe "high" version to satisfy >= constraints.
                mock_version = "999.9.9"
                if req.specifier:
                    # Pick the first explicit version found in the specifier (e.g., from '==')
                    for spec in req.specifier:
                        if spec.operator in ("==", ">=", "~="):
                            mock_version = spec.version
                            break
                
                warnings.warn(f"Mocking {pkg_name} with version {mock_version} to bypass requirements failure ({raw_failed_specs}).")
                micropip.add_mock_package(pkg_name, mock_version)

            # Retry to finalize the transaction for supported packages
            kwargs.pop("keep_going", None)
            await micropip.install(requirements, **kwargs)

    await graceful_install("build123d")

    # You can now include your own build123d script, as `import build123d` will work.
