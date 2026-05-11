"""
Applies WASM/ctypes compatibility fixes to ACT-generated Lib3MF.py files.

The generated bindings mix up pointer-sized and fixed-width integers on
WASM32/Pyodide. This patcher rewrites only the proven problematic cases:

- String-buffer getters:
  (..., uint64 bufferSize, uint64* neededChars, char* buffer)
  must use uint32/uint32* on WASM.
- Count-like outputs:
  functions whose name includes "count" and expose uint32* outputs must use
  uint64* so the wrapper matches the generated ABI expectations.
- Wrapper locals:
  local ctypes variables are rewritten from the callee signature that they are
  passed into, which also fixes newer functions such as getlibraryversion.
"""

from __future__ import annotations

import re
import sys


ARGTYPES_RE = re.compile(
    r"^(?P<indent>\s*)self\.lib\.(?P<name>lib3mf_\w+)\.argtypes = \[(?P<args>.*)\]\s*$"
)
METHOD_ASSIGN_RE = re.compile(
    r"^\s*self\.lib\.(?P<name>lib3mf_\w+)\s*=\s*methodType\("
)
CALL_START_RE = re.compile(r"lib\.(?P<name>lib3mf_\w+)\(")
ASSIGN_RE = re.compile(
    r"^(?P<indent>\s*)(?P<var>\w+)\s*=\s*ctypes\.(?P<ctype>c_uint32|c_uint64)\((?P<expr>.*)\)\s*$"
)
METHOD_DEF_RE = re.compile(r"^\s*def\s+\w+\(")


def split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def classify_argtypes(name: str, argtypes: list[str]) -> list[str]:
    fixed = list(argtypes)

    # String getter pattern:
    # [..., c_uint64, POINTER(c_uint64), c_char_p]
    for i in range(len(fixed) - 2):
        if (
            fixed[i] == "ctypes.c_uint64"
            and fixed[i + 1] == "ctypes.POINTER(ctypes.c_uint64)"
            and fixed[i + 2] == "ctypes.c_char_p"
        ):
            fixed[i] = "ctypes.c_uint32"
            fixed[i + 1] = "ctypes.POINTER(ctypes.c_uint32)"

    # Count outputs use 64-bit pointees in the generated WASM ABI.
    if "count" in name.lower():
        fixed = [
            "ctypes.POINTER(ctypes.c_uint64)"
            if arg == "ctypes.POINTER(ctypes.c_uint32)"
            else arg
            for arg in fixed
        ]

    return fixed


def desired_ctype_for_arg(argtype: str) -> str | None:
    if argtype in ("ctypes.c_uint32", "ctypes.POINTER(ctypes.c_uint32)"):
        return "c_uint32"
    if argtype in ("ctypes.c_uint64", "ctypes.POINTER(ctypes.c_uint64)"):
        return "c_uint64"
    return None


def collect_signature_map(lines: list[str]) -> dict[str, list[str]]:
    signatures: dict[str, list[str]] = {}
    for line in lines:
        match = ARGTYPES_RE.match(line)
        if not match:
            continue
        signatures[match.group("name")] = classify_argtypes(
            match.group("name"),
            split_top_level(match.group("args")),
        )
    return signatures


def rewrite_argtypes(lines: list[str], signatures: dict[str, list[str]]) -> list[str]:
    result: list[str] = []
    for line in lines:
        match = ARGTYPES_RE.match(line)
        if not match:
            result.append(line)
            continue
        name = match.group("name")
        new_args = ", ".join(signatures[name])
        result.append(f"{match.group('indent')}self.lib.{name}.argtypes = [{new_args}]")
    return result


def rewrite_methodtypes(lines: list[str], signatures: dict[str, list[str]]) -> list[str]:
    result = list(lines)
    for i, line in enumerate(lines[:-1]):
        if "methodType = ctypes.CFUNCTYPE(" not in line:
            continue
        assign_match = METHOD_ASSIGN_RE.match(lines[i + 1])
        if not assign_match:
            continue
        name = assign_match.group("name")
        if name not in signatures:
            continue

        prefix, inner = line.split("ctypes.CFUNCTYPE(", 1)
        if not inner.endswith(")"):
            continue
        params = split_top_level(inner[:-1])
        if len(params) < 1:
            continue

        restype = params[0]
        new_line = (
            f"{prefix}ctypes.CFUNCTYPE("
            + ", ".join([restype, *signatures[name]])
            + ")"
        )
        result[i] = new_line
    return result


def extract_call_signature_needs(block: list[str], signatures: dict[str, list[str]]) -> dict[str, str]:
    desired: dict[str, str] = {}

    for line in block:
        for match in CALL_START_RE.finditer(line):
            name = match.group("name")
            if name not in signatures:
                continue
            start = match.end()
            depth = 1
            end = start
            while end < len(line) and depth > 0:
                if line[end] == "(":
                    depth += 1
                elif line[end] == ")":
                    depth -= 1
                end += 1
            if depth != 0:
                continue

            args = split_top_level(line[start : end - 1])
            for expr, argtype in zip(args, signatures[name]):
                expr = expr.strip()
                ctype = desired_ctype_for_arg(argtype)
                if ctype is None or not re.fullmatch(r"\w+", expr):
                    continue
                if expr in desired and desired[expr] != ctype:
                    continue
                desired[expr] = ctype

    return desired


def rewrite_method_block(block: list[str], signatures: dict[str, list[str]]) -> list[str]:
    desired = extract_call_signature_needs(block, signatures)
    if not desired:
        return block

    result: list[str] = []
    for line in block:
        match = ASSIGN_RE.match(line)
        if not match:
            result.append(line)
            continue

        var = match.group("var")
        target = desired.get(var)
        if target is None or target == match.group("ctype"):
            result.append(line)
            continue

        result.append(
            f"{match.group('indent')}{var} = ctypes.{target}({match.group('expr')})"
        )
    return result


def rewrite_method_locals(lines: list[str], signatures: dict[str, list[str]]) -> list[str]:
    result: list[str] = []
    i = 0
    while i < len(lines):
        if not METHOD_DEF_RE.match(lines[i]):
            result.append(lines[i])
            i += 1
            continue

        block = [lines[i]]
        i += 1
        while i < len(lines) and not METHOD_DEF_RE.match(lines[i]):
            block.append(lines[i])
            i += 1
        result.extend(rewrite_method_block(block, signatures))
    return result


def fix_lib3mf(content: str) -> str:
    lines = content.splitlines()
    signatures = collect_signature_map(lines)
    lines = rewrite_argtypes(lines, signatures)
    lines = rewrite_methodtypes(lines, signatures)
    lines = rewrite_method_locals(lines, signatures)
    return "\n".join(lines) + ("\n" if content.endswith("\n") else "")


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: fix_lib3mf_wasm.py <input.py> <output.py>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        content = f.read()

    fixed = fix_lib3mf(content)

    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write(fixed)

    orig_lines = content.splitlines()
    new_lines = fixed.splitlines()
    changes = sum(1 for a, b in zip(orig_lines, new_lines) if a != b)
    changes += abs(len(orig_lines) - len(new_lines))
    print(f"Total lines changed: {changes}")


if __name__ == "__main__":
    main()
