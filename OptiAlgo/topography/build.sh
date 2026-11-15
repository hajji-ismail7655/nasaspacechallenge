#!/bin/bash
set -e
g++ -O3 -march=native -fopenmp -std=c++20 -shared -fPIC \
    -I include src/topography.cpp -o libtopography.so
echo "built libtopography.so"
