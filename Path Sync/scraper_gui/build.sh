#!/bin/bash

echo "========================================"
echo "  Path Sync - Build Script"
echo "========================================"
echo ""

cd "$(dirname "$0")"

echo "[1/2] Checking environment..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python not found! Please install Python 3.10+"
    exit 1
fi

echo "[2/2] Building executable..."
echo ""

pyinstaller Path-Sync.spec --clean

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Build failed!"
    exit 1
fi

echo ""
echo "========================================"
echo "  Build Complete!"
echo "========================================"
echo ""
echo "Output: dist/Path-Sync"
echo ""