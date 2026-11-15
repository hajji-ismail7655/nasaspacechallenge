#!/bin/bash
set -e
g++ -O3 -march=native -fopenmp -std=c++20 -shared -fPIC \
    -I include src/granular_aeolian.cpp -o libgranular_aeolian.so
echo "built libgranular_aeolian.so"
