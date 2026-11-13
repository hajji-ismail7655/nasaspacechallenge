#!/bin/bash
# Compile C++ module with AddressSanitizer + UBSan and run a smoke test.
set -e
MOD=${1:-topography}
TILE_EARTH=${2:-}
TILE_TARGET=${3:-}
SRC="src/${MOD}.cpp"
OUT="/tmp/scratchpad/${MOD}_asan"
mkdir -p /tmp/scratchpad
g++ -O1 -g -fsanitize=address,undefined -fopenmp -std=c++20 -shared -fPIC \
    -I include "$SRC" -o "${OUT}.so"
echo "ASAN build OK for $MOD"
if [[ -n "$TILE_EARTH" && -n "$TILE_TARGET" ]]; then
  ASAN_RUNTIME=$(g++ -print-file-name=libasan.so)
  LD_PRELOAD="${ASAN_RUNTIME}${LD_PRELOAD:+:${LD_PRELOAD}}" \
    python3 - "$MOD" "$TILE_EARTH" "$TILE_TARGET" "${OUT}.so" << 'PYEOF'
import ctypes, sys, os
mod, earth, target, lib = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
L = ctypes.CDLL(lib)
L.run_module.argtypes = [ctypes.c_char_p]*4
L.run_module.restype = ctypes.c_int32
out_h = "/tmp/scratchpad/asan.hmap"
out_b = "/tmp/scratchpad/asan.json"
rc = L.run_module(earth.encode(), target.encode(), out_h.encode(), out_b.encode())
print("run_module rc =", rc)
assert rc == 0
print("ASAN smoke test PASSED")
PYEOF
fi
exit 0
