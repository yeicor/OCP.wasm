import subprocess
import sys
import os
import shutil
import re

def get_error_offset(wasm_file):
    try:
        subprocess.run(
            ['wasm-opt', '--no-validation', '--enable-exception-handling', '-O0', wasm_file, '-o', os.devnull],
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            check=True
        )
        return None  # No errors
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode()
        print(stderr)
        for line in stderr.splitlines():
            all_non_zero_integers = re.findall(r'[1-9][0-9]*', line)
            if all_non_zero_integers:
                return int(all_non_zero_integers[0])
        raise RuntimeError(f"Could not parse offset from wasm-opt stderr:\n{stderr}")

def patch_wasm(wasm_bytes, error_offset):
    start = error_offset
    while start >= 0 and wasm_bytes[start] != 0x0E:
        start -= 1
    if start < 0:
        raise RuntimeError(f"Could not find br_table (0x0E) before the error offset at {error_offset}.")
    print(f"Fixing invalid instruction at bytes [{start}, {error_offset}]...")
    for i in range(start, error_offset + 1):
        wasm_bytes[i] = 0x00  # Replace with 'unreachable'
    return wasm_bytes

def repair_and_optimize_wasm(input_path, output_path):
    print(f"Copying and repairing: {input_path}")
    with open(input_path, 'rb') as f:
        wasm_bytes = bytearray(f.read())

    fixed_path = input_path + '.fixed.wasm'

    while True:
        with open(fixed_path, 'wb') as f:
            f.write(wasm_bytes)

        print("Looking for (more) errors...")
        offset = get_error_offset(fixed_path)
        if offset is None:
            break  # All errors fixed

        wasm_bytes = patch_wasm(wasm_bytes, offset)
        
    is_debug = os.environ.get("DEBUG", "").lower() in {"1", "on", "true", "yes"}
    opt_level = "-O2" if is_debug else "-O4"

    print("Patching complete. Starting optimization (" + opt_level + ")...")

    subprocess.run(
        ['wasm-opt', '--no-validation', '--enable-exception-handling', '--post-emscripten', opt_level,
         fixed_path, '-o', output_path],
        check=True
    )

    os.remove(fixed_path)
    print(f"Optimized WebAssembly written to: {output_path}")

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python repair_and_optimize_wasm.py <input_dir> <output_dir>")
        sys.exit(1)
        
    # Find the actual input and output paths... (CMake is hard)
    input_dir = sys.argv[1]
    output_dir = sys.argv[2]
    os.makedirs(output_dir, exist_ok=True)

    # Find the first .wasm file in the input directory
    wasm_files = [f for f in os.listdir(input_dir) if f.endswith('.wasm') or f.endswith('.so')]
    if len(wasm_files) != 1:
        print(f"No wasm/so file or too many wasm/so files found ({wasm_files}) in input directory: {input_dir}")
        sys.exit(1)

    input_filename = wasm_files[0]
    input_path = os.path.join(input_dir, input_filename)
    output_path = os.path.join(output_dir, input_filename)

    repair_and_optimize_wasm(input_path, output_path)
