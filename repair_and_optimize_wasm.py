import subprocess
import sys
import os
import shutil
import re

def get_error_offset(wasm_file):
    try:
        subprocess.run(
            ['wasm-dis', '--enable-exception-handling', wasm_file, '-o', os.devnull],
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            check=True
        )
        return None  # No errors
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode()
        for line in stderr.splitlines():
            all_non_zero_integers = re.findall('[0-9]+', line)
            print(f"all_non_zero_integers {all_non_zero_integers}")
            if len(all_non_zero_integers) > 1:
                return int(all_non_zero_integers[1])
        raise RuntimeError(f"Could not parse offset from wasm-dis stderr: {stderr} | {all_non_zero_integers}")

def patch_wasm(wasm_bytes, error_offset):
    start = error_offset
    while start >= 0 and wasm_bytes[start] != 0x0E:
        start -= 1
    if start < 0:
        raise RuntimeError(f"Could not find br_table (0x0E) before the error offset off {error_offset}.")
    print(f"Fixing invalid instruction at bytes [{start}, {error_offset}]...")
    for i in range(start, error_offset + 1):
        wasm_bytes[i] = 0x00  # Replace with 'unreachable'
    return wasm_bytes

def repair_and_optimize_wasm(wasm_path):
    print(f"Copying {wasm_path} to fix it...")
    with open(wasm_path, 'rb') as f:
        wasm_bytes = bytearray(f.read())

    fixed_path = wasm_path + '.fixed.wasm'

    while True:
        with open(fixed_path, 'wb') as f:
            f.write(wasm_bytes)

        print(f"Looking for (more) errors...")
        offset = get_error_offset(fixed_path)
        if offset is None:
            break  # Success

        wasm_bytes = patch_wasm(wasm_bytes, offset)

    print("Patches complete, optimizing \"fixed\" build")
    optimized_path = wasm_path + '.opt.wasm'
    subprocess.run(
        ['wasm-opt', '--no-validation', '--enable-exception-handling', '-O4', fixed_path, '-o', optimized_path],
        env={'BINARYEN_PASS_DEBUG': 1}
        check=True
    )
    shutil.move(optimized_path, wasm_path)
    os.remove(fixed_path)
    print("WASM file successfully patched and optimized.")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: python repair_and_optimize_wasm.py <wasm_file>")
        sys.exit(1)
    repair_and_optimize_wasm(sys.argv[1])
