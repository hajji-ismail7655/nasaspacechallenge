#!/bin/bash
set -e
g++ -O3 -march=native -fopenmp -std=c++20 -shared -fPIC \
    -I include src/thermal_illumination.cpp -o libthermal_illumination.so
echo "built libthermal_illumination.so"
