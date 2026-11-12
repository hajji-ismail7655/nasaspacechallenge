#!/bin/bash
set -e
g++ -O3 -march=native -fopenmp -std=c++20 -shared -fPIC \
    -I include src/volatiles_subsurface.cpp -o libvolatiles_subsurface.so
echo "built libvolatiles_subsurface.so"
