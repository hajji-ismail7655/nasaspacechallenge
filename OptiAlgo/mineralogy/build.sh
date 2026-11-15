#!/bin/bash
set -e
g++ -O3 -march=native -fopenmp -std=c++20 -shared -fPIC \
    -I include src/mineralogy.cpp -o libmineralogy.so
echo "built libmineralogy.so"
