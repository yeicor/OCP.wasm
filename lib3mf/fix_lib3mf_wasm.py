"""
Applies WASM/ctypes compatibility fixes to the ACT-generated Lib3MF.py.

On WASM (Pyodide/Emscripten):
  - ctypes.CFUNCTYPE cannot register callbacks with c_uint64 parameters
    (WASM32 ABI has no 64-bit integer support for function signatures).
  - Buffer size parameters (uint64_t in native API) must be uint32_t on WASM.
  - Count output parameters (uint32_t*) remain as pointer types but the
    pointee type must match what the library actually writes.

This script transforms the auto-generated Lib3MF.py to work on WASM.
It is designed to be resilient across ACT-generated version bumps:
new functions following the same patterns are automatically handled.
"""

import re


def fix_lib3mf(content: str) -> str:
    lines = content.split("\n")
    result = []

    # Match: standalone ctypes.c_uint64 (not inside POINTER) followed by:
    #   ...POINTER(ctypes.c_uint64), ctypes.c_char_p
    # (the buffer-string-getter pattern — the only context the proven patch changes)
    _RE_BUF_GETTER = re.compile(
        r"(?<!POINTER\()ctypes\.c_uint64"
        r"(.*?POINTER\(ctypes\.c_uint64\),\s*ctypes\.c_char_p)"
    )

    for i, raw_line in enumerate(lines):
        line = raw_line

        is_indented = line.startswith((" ", "\t"))
        is_callback_def = line.strip().startswith((
            "ProgressCallback", "WriteCallback", "ReadCallback",
            "SeekCallback", "RandomNumberCallback", "KeyWrappingCallback",
            "ContentEncryptionCallback",
        ))

        # ── Transform 1: CFUNCTYPE (inside methods) ──────────────────
        if is_indented and "CFUNCTYPE" in line and not is_callback_def:
            # 1a: POINTER(c_uint32) → POINTER(c_uint64)  (count outputs)
            # Only change for count functions (function name in next line)
            if "POINTER(ctypes.c_uint32)" in raw_line:
                _fn_match = None
                if i + 1 < len(lines):
                    _fn_match = re.search(r"lib3mf_(\w+)", lines[i + 1])
                if _fn_match and "count" in _fn_match.group(1).lower():
                    line = line.replace("POINTER(ctypes.c_uint32)", "POINTER(ctypes.c_uint64)")

            # 1b: standalone c_uint64, POINTER(c_uint64), c_char_p → c_uint32, POINTER(c_uint32), c_char_p
            line = _RE_BUF_GETTER.sub(
                lambda m: "ctypes.c_uint32"
                + m.group(1).replace(
                    "POINTER(ctypes.c_uint64)", "POINTER(ctypes.c_uint32)"
                ),
                line,
            )

        # ── Transform 2: argtypes ────────────────────────────────────
        if ".argtypes" in line:
            # 2a: POINTER(c_uint32) → POINTER(c_uint64)  (count outputs)
            # Only change for count functions
            if "POINTER(ctypes.c_uint32)" in raw_line:
                _fn_match = re.search(r"lib3mf_(\w+)\.argtypes", raw_line)
                if _fn_match and "count" in _fn_match.group(1).lower():
                    line = line.replace("POINTER(ctypes.c_uint32)", "POINTER(ctypes.c_uint64)")

            # 2b: standalone c_uint64, POINTER(c_uint64), c_char_p → c_uint32, POINTER(c_uint32), c_char_p
            line = _RE_BUF_GETTER.sub(
                lambda m: "ctypes.c_uint32"
                + m.group(1).replace(
                    "POINTER(ctypes.c_uint64)", "POINTER(ctypes.c_uint32)"
                ),
                line,
            )

        # ── Transform 3: Method-body code (indented, non-signature) ──
        if is_indented and "CFUNCTYPE" not in line and ".argtypes" not in line:
            # 3a: ctypes.c_uint64(0) → ctypes.c_uint32(0)  (buffer-size init)
            line = re.sub(r"\bctypes\.c_uint64\(0\)", "ctypes.c_uint32(0)", line)

            # 3b: ctypes.c_uint64(name.value) → ctypes.c_uint32(name.value)  (re-assignment)
            line = re.sub(
                r"\bctypes\.c_uint64\((\w+\.value)\)", r"ctypes.c_uint32(\1)", line
            )

            # 3c: ctypes.c_uint64(StreamSize) → ctypes.c_uint32(StreamSize)
            line = re.sub(
                r"\bctypes\.c_uint64\((StreamSize)\)", r"ctypes.c_uint32(\1)", line
            )

            # 3d: pCount|c|SheetCount = ctypes.c_uint32() → ctypes.c_uint64()
            line = re.sub(
                r"(p(?:Count|RowCount|ColumnCount|SheetCount))\s*=\s*ctypes\.c_uint32\(\)",
                r"\1 = ctypes.c_uint64()",
                line,
            )

            # 3e: ctypes.c_uint32((Row|Column|Sheet)Count) → ctypes.c_uint64(...)
            line = re.sub(
                r"\bctypes\.c_uint32\(((?:Row|Column|Sheet)Count)\)",
                r"ctypes.c_uint64(\1)",
                line,
            )

        result.append(line)

    return "\n".join(result)


def main():
    import sys

    if len(sys.argv) != 3:
        print("Usage: fix_lib3mf_wasm.py <input.py> <output.py>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        content = f.read()

    fixed = fix_lib3mf(content)

    with open(sys.argv[2], "w") as f:
        f.write(fixed)

    orig_lines = content.split("\n")
    new_lines = fixed.split("\n")
    changes = sum(1 for a, b in zip(orig_lines, new_lines) if a != b)
    print(f"Total lines changed: {changes}")


if __name__ == "__main__":
    main()
