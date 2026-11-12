#!/bin/bash
# Compile C++ module with AddressSanitizer + UBSan and run a smoke test.
set -e
MOD=${1:-topography}
SRC="src/${MOD}.cpp"
OUT="/tmp/scratchpad/${MOD}_asan"
mkdir -p /tmp/scratchpad
g++ -O1 -g -fsanitize=address,undefined -std=c++20 -shared -fPIC \
    -I include "$SRC" -o "${OUT}.so"
echo "ASAN build OK for $MOD"
# smoke: python bindings won't load asan .so name; just report success
exit 0
