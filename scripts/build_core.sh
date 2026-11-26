#!/usr/bin/env bash
# Builds the C++20 core and the pybind11 module (ninja, release).
set -euo pipefail
cd "$(dirname "$0")/.."

cmake -S core -B core/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build core/build
./core/build/core_tests
echo
echo "module: app/legalgit_core*.so"
