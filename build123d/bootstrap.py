from __future__ import annotations

import asyncio
import importlib.metadata
import io
import json
import logging
import os
import re
import shlex
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

logger = logging.getLogger("build123d_bootstrap")

try:
    import micropip  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    micropip = None

try:
    from pyodide.http import pyfetch  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    pyfetch = None


_OCP_VARIANTS: list[tuple[str, list[str]]] = [
    ("cadquery-ocp-novtk", ["cadquery-ocp", "cadquery-ocp-novtk"]),
    ("lib3mf", ["lib3mf", "py-lib3mf"]),
]

_PYPI_JSON_CACHE: dict[str, dict[str, Any]] = {}


@dataclass(slots=True)
class InstallPlan:
    """Resolved installation plan for build123d."""

    source: str
    version: str
    ref: str
    ocp_specifiers: dict[str, str]


class _NormalizedResponse:
    """Normalize pyfetch and urllib responses to a common async API."""

    def __init__(self, response: Any, is_emscripten: bool):
        self._response = response
        self._is_emscripten = is_emscripten

    @property
    def status(self) -> int:
        return (
            self._response.status
            if self._is_emscripten
            else self._response.code
        )

    def get_header(self, name: str) -> str | None:
        if self._is_emscripten:
            return self._response.headers.get(name)
        return self._response.getheader(name)

    async def text(self) -> str:
        if self._is_emscripten:
            return await self._response.text()
        return self._response.read().decode("utf-8")

    async def bytes(self) -> bytes:
        if self._is_emscripten:
            return await self._response.bytes()
        return self._response.read()

    async def json(self) -> dict[str, Any]:
        if self._is_emscripten:
            return await self._response.json()
        return json.load(self._response)


def _platform_is_emscripten() -> bool:
    """Return True when running under Pyodide/Emscripten."""
    return sys.platform == "emscripten"


def _normalize_constraints(
    constraints: (
        Sequence[Any]
        | Mapping[str, Any]
        | str
        | os.PathLike[str]
        | None
    ),
) -> list[str]:
    """Normalize user constraints into pip-compatible constraint lines.

    Supported inputs:
    - sequence of strings
    - mapping of package -> version specifier
    - path to constraints file
    - inline constraints string
    """

    if constraints is None:
        return []

    lines: list[str] = []

    if isinstance(constraints, Mapping):
        for package, spec in constraints.items():
            package = str(package).strip()
            spec = str(spec).strip()
            if not package:
                continue

            if spec and not spec.startswith(
                ("=", "<", ">", "~", "!")
            ):
                spec = f"=={spec}"

            lines.append(f"{package}{spec}")
        return sorted(set(lines))

    if isinstance(constraints, (str, os.PathLike)):
        raw = os.fspath(constraints)

        if (
            isinstance(constraints, str)
            and "\n" not in raw
            and Path(raw).is_file()
        ):
            text = Path(raw).read_text(encoding="utf-8")
        else:
            text = raw

        items = text.splitlines()
    else:
        items = []

        for entry in constraints:
            if entry is None:
                continue
            items.extend(str(entry).splitlines())

    for line in items:
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        lines.append(stripped)

    return sorted(set(lines))


async def _fetch(url: str) -> _NormalizedResponse:
    """Fetch a URL using pyfetch or urllib depending on the platform."""

    is_emscripten = _platform_is_emscripten()

    logger.debug(
        "Fetching URL: %s (platform=%s)",
        url,
        "Pyodide" if is_emscripten else "native",
    )

    if is_emscripten:
        if pyfetch is None:
            raise RuntimeError(
                "pyfetch is not available in this Pyodide environment"
            )

        try:
            response = await pyfetch(url)
        except Exception as exc:
            logger.warning(
                "pyfetch failed for %s (%s); retrying through CORS proxy",
                url,
                exc,
            )

            import urllib.parse

            proxied = (
                "https://little-hill-4bc4.yeicor-cloudflare.workers.dev/?url="
                + urllib.parse.quote_plus(url)
            )

            response = await pyfetch(proxied)
    else:
        import urllib.request

        response = urllib.request.urlopen(url)

    return _NormalizedResponse(response, is_emscripten)


async def _fetch_text(url: str) -> str:
    """Fetch a URL and return text."""
    return await (await _fetch(url)).text()


async def _fetch_bytes(url: str) -> bytes:
    """Fetch a URL and follow redirects."""

    max_redirects = 5

    for attempt in range(1, max_redirects + 1):
        logger.debug("_fetch_bytes attempt %d for %s", attempt, url)

        response = await _fetch(url)
        status = response.status

        if 300 <= status < 400:
            location = response.get_header("Location")

            if not location:
                raise RuntimeError(
                    f"Redirect without Location header for {url}"
                )

            logger.info("Redirect %s -> %s", url, location)
            url = location
            continue

        if 200 <= status < 300:
            return await response.bytes()

        raise RuntimeError(f"Failed to fetch {url}: HTTP {status}")

    raise RuntimeError(f"Too many redirects while fetching {url}")


async def _get_pypi_json(
    package: str,
    version: str | None = None,
) -> dict[str, Any]:
    """Fetch package metadata from PyPI with in-process caching."""

    url = f"https://pypi.org/pypi/{package}"

    if version:
        url += f"/{version}"

    url += "/json"

    if url in _PYPI_JSON_CACHE:
        logger.debug("PyPI JSON cache hit: %s", url)
        return _PYPI_JSON_CACHE[url]

    logger.info(
        "Fetching PyPI JSON for %s (version=%s)",
        package,
        version,
    )

    data = await (await _fetch(url)).json()

    _PYPI_JSON_CACHE[url] = data

    return data


def _extract_ocp_specifiers(
    requirements: Iterable[str],
) -> dict[str, str]:
    """Extract OCP-related requirement specifiers."""

    ocp_specifiers: dict[str, str] = {}

    for req in requirements:
        req = req.replace("(", "").replace(")", "").strip()

        if not req:
            continue

        if ";" in req:
            req = req.split(";", 1)[0].strip()

        req_name = re.split(
            r">=|>|<=|<|~=|==|!=",
            req,
        )[0].strip()

        for canonical, variants in _OCP_VARIANTS:
            if req_name in variants:
                suffix = req[len(req_name) :].lstrip()

                ocp_specifiers[canonical] = suffix

                logger.debug(
                    "Matched requirement %s -> %s suffix=%r",
                    req_name,
                    canonical,
                    suffix,
                )

                break

    return ocp_specifiers


def _build_requirement_argv(requirement: str) -> list[str]:
    """Convert a requirement string into pip argv fragments."""

    if requirement.startswith("-"):
        return shlex.split(requirement)

    return [requirement]


async def _platform_install(
    requirement: str | Sequence[str],
    *,
    constraints: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    """Install packages on either Pyodide or native Python."""

    constraint_lines = list(constraints or [])

    logger.info("Installing: %s", requirement)

    if _platform_is_emscripten():
        if micropip is None:
            raise RuntimeError(
                "micropip is not available in this environment"
            )

        kwargs: dict[str, Any] = {
            "reinstall": True,
            "keep_going": True,
        }

        if constraint_lines:
            kwargs["constraints"] = constraint_lines

        req = (
            list(requirement)
            if not isinstance(requirement, str)
            else requirement
        )

        logger.debug("micropip.install(%r, %s)", req, kwargs)

        await micropip.install(req, **kwargs)

        if constraint_lines and hasattr(micropip, "set_constraints"):
            try:
                micropip.set_constraints(constraint_lines)
            except Exception:
                logger.debug(
                    "micropip.set_constraints failed; continuing"
                )

        return

    import subprocess
    
    args = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--force-reinstall",
    ]

    constraint_file = None

    try:
        if constraint_lines:
            with tempfile.NamedTemporaryFile(
                "w",
                suffix=".txt",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                tmp.write("\n".join(constraint_lines))
                tmp.write("\n")

                constraint_file = tmp.name

            args.extend(["-c", constraint_file])

        if isinstance(requirement, str):
            args.extend(_build_requirement_argv(requirement))
        else:
            args.extend(requirement)

        logger.debug(
            "Running native install: %s",
            " ".join(shlex.quote(arg) for arg in args),
        )

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **(env or {})},
        )

        stdout, stderr = await proc.communicate()

        if stdout:
            logger.debug(
                "pip stdout:\n%s",
                stdout.decode(errors="replace"),
            )

        if proc.returncode != 0:
            err_text = stderr.decode(errors="replace")

            logger.error(
                "pip failed with code %s:\n%s",
                proc.returncode,
                err_text,
            )

            raise RuntimeError(
                f"Failed to install package {requirement!r}:\n{err_text}"
            )

        logger.debug("pip install succeeded for %s", requirement)

    finally:
        if constraint_file:
            try:
                os.unlink(constraint_file)
            except FileNotFoundError:
                pass


async def _find_latest_dev_version(
    package_name: str,
    version_spec: str,
    *,
    constraints: Sequence[str] | None = None,
) -> str:
    """Find the newest matching .dev version on PyPI."""

    logger.info(
        "Looking for latest .dev version for %s (spec=%s)",
        package_name,
        version_spec,
    )

    data = await _get_pypi_json(package_name)

    releases = data.get("releases", {})

    await _platform_install(
        "packaging",
        constraints=constraints,
    )

    import packaging.specifiers
    import packaging.version

    spec = (
        packaging.specifiers.SpecifierSet(version_spec)
        if version_spec
        else None
    )

    dev_versions: list[str] = []

    for version in releases:
        if ".dev" not in version:
            continue

        try:
            parsed = packaging.version.parse(version)
        except Exception:
            continue

        if spec is None:
            dev_versions.append(version)
            continue

        if parsed in spec:
            dev_versions.append(version)
            continue

        try:
            base = packaging.version.parse(parsed.base_version)

            if base in spec:
                dev_versions.append(version)
        except Exception:
            pass

    if not dev_versions:
        logger.warning(
            "No matching .dev versions found for %s",
            package_name,
        )

        return version_spec

    dev_versions.sort(
        key=packaging.version.parse,
        reverse=True,
    )

    latest = dev_versions[0]

    logger.info(
        "Using .dev version %s for %s",
        latest,
        package_name,
    )

    return f"=={latest}"


async def _resolve_pypi_plan(ref: str) -> InstallPlan:
    """Resolve a PyPI install plan."""

    data = await _get_pypi_json("build123d", ref)

    version = data["info"]["version"]

    requirements = data["info"].get("requires_dist", [])

    ocp_specifiers = _extract_ocp_specifiers(requirements)

    return InstallPlan(
        source="pypi",
        version=version,
        ref=ref,
        ocp_specifiers=ocp_specifiers,
    )


async def _resolve_github_plan(ref: str) -> InstallPlan:
    """Resolve a GitHub source install plan."""

    logger.debug(
        "Resolving build123d dependencies from GitHub ref %s",
        ref,
    )

    pyproject_url = (
        f"https://raw.githubusercontent.com/"
        f"gumyr/build123d/{ref}/pyproject.toml"
    )

    content = await _fetch_text(pyproject_url)

    import tomllib

    try:
        pyproject = tomllib.loads(content)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to parse pyproject.toml for {ref}: {exc}"
        ) from exc

    requirements = (
        pyproject.get("project", {}).get("dependencies", [])
    )

    ocp_specifiers = _extract_ocp_specifiers(requirements)

    if re.match(r"^v?\d+\.\d+\.\d+$", ref):
        version = ref.removeprefix("v")
    else:
        try:
            latest = (
                await _get_pypi_json("build123d")
            )["info"]["version"]

            version = (
                f"{latest}+"
                f"{ref.replace('.', '_').replace('/', '_')}"
            )
        except Exception as exc:
            logger.warning(
                "Could not fetch latest stable version: %s",
                exc,
            )

            version = (
                f"0.0.0+"
                f"{ref.replace('.', '_').replace('/', '_')}"
            )

    return InstallPlan(
        source="github",
        version=version,
        ref=ref,
        ocp_specifiers=ocp_specifiers,
    )


def _find_build123d_sources() -> str | None:
    """Find the installed build123d source directory."""

    import site

    site_packages_dirs = (
        site.getsitepackages() + [site.getusersitepackages()]
    )

    for site_pkg in site_packages_dirs:
        for candidate in ("build123d-src", "build123d"):
            path = os.path.join(site_pkg, candidate)

            if os.path.isdir(path):
                return path

    return None


async def _install_ocp_wasm_wheels(
    ocp_specifiers: Mapping[str, str],
    *,
    constraints: Sequence[str] | None = None,
    debug: bool = False,
):
    """Install OCP WASM wheels and create Pyodide mock packages."""

    logger.info(
        "Installing OCP WASM wheels (debug=%s)",
        debug,
    )

    mocked_packages: list[str] = []

    try:
        installs = []

        for canonical_name, _ in _OCP_VARIANTS:
            spec = ocp_specifiers.get(canonical_name, "")

            wheel_name = f"{canonical_name}-OCP.wasm"

            if debug:
                spec = await _find_latest_dev_version(
                    wheel_name,
                    spec,
                    constraints=constraints,
                )

            installs.append(
                await _platform_install(
                    f"{wheel_name}{spec}",
                    constraints=constraints,
                )
            )

        await asyncio.gather(*installs)

        if _platform_is_emscripten():
            await _platform_install(
                "sqlite3",
                constraints=constraints,
            )

        if _platform_is_emscripten() and micropip is not None:
            for canonical_name, mock_names in _OCP_VARIANTS:
                wheel_name = f"{canonical_name}-OCP.wasm"

                version = importlib.metadata.version(wheel_name)

                for mock_name in mock_names:
                    mocked_packages.append(mock_name)

                    if mock_name == "py-lib3mf":
                        micropip.add_mock_package(
                            mock_name,
                            version,
                            modules={
                                "py_lib3mf": "from lib3mf import *"
                            },
                        )
                    else:
                        micropip.add_mock_package(
                            mock_name,
                            version,
                        )

        async def cleanup_mocks():
            """Remove all created mock packages."""

            if (
                _platform_is_emscripten()
                and micropip is not None
            ):
                for mock_name in mocked_packages:
                    logger.debug(
                        "Removing mock package %s",
                        mock_name,
                    )

                    micropip.remove_mock_package(mock_name)

        return cleanup_mocks

    except Exception:
        if _platform_is_emscripten() and micropip is not None:
            for mock_name in mocked_packages:
                try:
                    micropip.remove_mock_package(mock_name)
                except Exception:
                    pass

        raise


async def _install_from_pypi(
    version: str,
    *,
    constraints: Sequence[str] | None = None,
) -> None:
    """Install build123d from PyPI."""

    await _platform_install(
        f"build123d=={version}",
        constraints=constraints,
    )


async def _install_from_github(
    ref: str,
    *,
    version: str,
    constraints: Sequence[str] | None = None,
) -> None:
    """Install build123d directly from GitHub sources."""

    import shutil
    import tomllib

    zip_url = (
        f"https://github.com/gumyr/build123d/archive/{ref}.zip"
    )

    logger.debug("Downloading %s", zip_url)

    sources_bytes = await _fetch_bytes(zip_url)

    tmpdir = tempfile.TemporaryDirectory()

    try:
        with zipfile.ZipFile(
            file=io.BytesIO(sources_bytes),
            mode="r",
        ) as zipf:
            zipf.extractall(path=tmpdir.name)

        extracted_dir = os.path.join(
            tmpdir.name,
            os.listdir(tmpdir.name)[0],
        )

        sources_folder = os.path.join(extracted_dir, "src")

        version_py = os.path.join(
            sources_folder,
            "build123d",
            "version.py",
        )

        os.makedirs(os.path.dirname(version_py), exist_ok=True)

        with open(version_py, "w", encoding="utf-8") as f:
            f.write(
                f"version = {version!r}\n"
                "__version__ = version\n"
            )

        with open(
            os.path.join(extracted_dir, "pyproject.toml"),
            "rb",
        ) as f:
            pyproject = tomllib.load(f)

        deps = (
            pyproject.get("project", {}).get("dependencies", [])
        )

        if os.getenv(
            "_install_build123d_from_github_also_optional",
            "",
        ):
            optional = (
                pyproject.get("project", {})
                .get("optional-dependencies", {})
            )

            deps += optional.get("development", [])
            deps += optional.get("benchmark", [])

        install_tasks = []

        for dep in deps:
            dep = dep.strip()

            if (
                not dep
                or dep.startswith("lib3mf")
                or dep.startswith("cadquery-ocp")
                or dep == "mypy"
            ):
                continue

            install_tasks.append(
                _platform_install(
                    dep,
                    constraints=constraints,
                )
            )

        if install_tasks:
            await asyncio.gather(*install_tasks)

        if _platform_is_emscripten():
            import site

            site_packages = site.getsitepackages()[0]

            dest_base = os.path.join(
                site_packages,
                "build123d-src",
            )

            dest_src = os.path.join(dest_base, "src")

            os.makedirs(dest_src, exist_ok=True)

            shutil.rmtree(
                os.path.join(dest_src, "build123d"),
                ignore_errors=True,
            )

            shutil.copytree(
                os.path.join(sources_folder, "build123d"),
                os.path.join(dest_src, "build123d"),
            )

            for item in os.listdir(extracted_dir):
                if item in (
                    "src",
                    ".git",
                    ".gitignore",
                ):
                    continue

                src = os.path.join(extracted_dir, item)
                dst = os.path.join(dest_base, item)

                if os.path.isdir(src):
                    shutil.rmtree(
                        dst,
                        ignore_errors=True,
                    )

                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

            if dest_src not in sys.path:
                sys.path.insert(0, dest_src)

            dist_info_dir = os.path.join(
                site_packages,
                f"build123d-{version}.dist-info",
            )

            os.makedirs(dist_info_dir, exist_ok=True)

            files = [
                (
                    "METADATA",
                    (
                        "Metadata-Version: 2.1\n"
                        "Name: build123d\n"
                        f"Version: {version}\n"
                    ),
                ),
                (
                    "WHEEL",
                    (
                        "Wheel-Version: 1.0\n"
                        "Generator: build123d-bootstrap\n"
                        "Root-Is-Purelib: true\n"
                        "Tag: py3-none-any\n"
                    ),
                ),
                ("RECORD", ""),
                ("entry_points.txt", ""),
            ]

            for filename, content in files:
                with open(
                    os.path.join(dist_info_dir, filename),
                    "w",
                    encoding="utf-8",
                ) as f:
                    f.write(content)

            logger.info(
                "Installed build123d sources to %s",
                dest_base,
            )
        else:
            await _platform_install(
                f"-e {extracted_dir}",
                constraints=constraints,
                env={
                    "SETUPTOOLS_SCM_PRETEND_VERSION": version
                },
            )

    finally:
        tmpdir.cleanup()


async def _call_hook(hook: Any) -> None:
    """Invoke a sync or async hook."""

    result = hook()

    if asyncio.iscoroutine(result):
        await result


async def bootstrap(
    build123d_ref: str = "stable",
    debug: bool = False,
    constraints: (
        Sequence[Any]
        | Mapping[str, Any]
        | str
        | os.PathLike[str]
        | None
    ) = None,
    mocked_hook=None,
) -> str | None:
    """Bootstrap build123d into the current environment.
    All arguments are optional.

    Args:
        build123d_ref:
            One of:
            - ``"stable"``
            - ``"github:stable"``
            - a PyPI version like ``"0.8.0"``
            - a GitHub ref like ``"main"``, ``"dev"``, a tag,
              branch, PR ref, or commit hash.

            Prefix with ``"github:"`` to force a GitHub source install.

        debug:
            When True, prefer the newest matching ``.dev`` OCP WASM
            wheel versions instead of stable releases.

        constraints:
            Optional global package constraints applied to every install.

            Accepted formats:
            - sequence of constraint strings
            - mapping of package -> version specifier
            - path to constraints file
            - inline constraints text blob

            Examples:
                {"numpy": "<2", "typing-extensions": ">=4.10"}

                ["numpy<2", "packaging>=24"]

                "numpy<2\\npackaging>=24"

                "/path/to/constraints.txt"

        mocked_hook:
            Optional sync or async callable executed after all packages
            are installed but before Pyodide mock packages are removed.

    Returns:
        Path to the installed build123d sources or package directory,
        or ``None`` if no installation path could be located.

    Raises:
        RuntimeError:
            When network fetches, dependency resolution, or package
            installations fail.
    """

    logger.debug(
        "Bootstrapping build123d (ref=%s, debug=%s)",
        build123d_ref,
        debug,
    )

    constraint_lines = _normalize_constraints(constraints)

    if constraint_lines:
        logger.info(
            "Using %d constraint(s)",
            len(constraint_lines),
        )

        logger.debug(
            "Constraints: %s",
            constraint_lines,
        )

    if build123d_ref in {"stable", "github:stable"}:
        logger.debug(
            "Resolving latest stable build123d version"
        )

        latest = (
            await _get_pypi_json("build123d")
        )["info"]["version"]

        build123d_ref = (
            latest
            if build123d_ref == "stable"
            else f"github:v{latest}"
        )

        logger.debug(
            "Resolved stable ref to %s",
            build123d_ref,
        )

    if build123d_ref.startswith("github:"):
        plan = await _resolve_github_plan(
            build123d_ref.removeprefix("github:")
        )
    else:
        try:
            plan = await _resolve_pypi_plan(build123d_ref)
        except Exception as exc:
            logger.warning(
                "Could not resolve %s on PyPI (%s); "
                "falling back to GitHub",
                build123d_ref,
                exc,
            )

            plan = await _resolve_github_plan(
                build123d_ref
            )

    cleanup_mocks = await _install_ocp_wasm_wheels(
        plan.ocp_specifiers,
        constraints=constraint_lines,
        debug=debug,
    )

    try:
        if plan.source == "pypi":
            logger.debug(
                "Installing build123d %s from PyPI",
                plan.version,
            )

            await _install_from_pypi(
                plan.version,
                constraints=constraint_lines,
            )
        else:
            logger.debug(
                "Installing build123d from GitHub ref %s",
                plan.ref,
            )

            await _install_from_github(
                plan.ref,
                version=plan.version,
                constraints=constraint_lines,
            )

        if mocked_hook is not None:
            logger.debug(
                "Running mocked_hook before cleanup"
            )

            await _call_hook(mocked_hook)

    finally:
        await cleanup_mocks()

    sources = _find_build123d_sources()

    logger.debug(
        "Bootstrap complete. sources=%s",
        sources,
    )

    return sources
