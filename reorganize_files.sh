#!/usr/bin/env bash
# ============================================================================
#  reorganize_files.sh
#  Move loose notebooks and scripts from repo root into ai-services/
# ============================================================================

set -euo pipefail

cd /Users/akash/Desktop/minor

echo "==========================================="
echo "  Step 1 — Create target directories"
echo "==========================================="
mkdir -p ai-services/notebooks
mkdir -p ai-services/scripts

echo "==========================================="
echo "  Step 2 — Restore deleted notebooks from git"
echo "==========================================="
# These are tracked by git but deleted from disk — restore them first
git checkout HEAD -- car.ipynb car_object_detattion.ipynb object_detaction.ipynb yolov11.ipynb

echo "==========================================="
echo "  Step 3 — git mv notebooks into ai-services/notebooks/"
echo "==========================================="
git mv car.ipynb                    ai-services/notebooks/car.ipynb
git mv car_object_detattion.ipynb   ai-services/notebooks/car_object_detattion.ipynb
git mv object_detaction.ipynb       ai-services/notebooks/object_detaction.ipynb
git mv yolov11.ipynb                ai-services/notebooks/yolov11.ipynb
echo "✅ Notebooks moved"

echo "==========================================="
echo "  Step 4 — git mv script into ai-services/scripts/"
echo "==========================================="
git mv cardetect.py                 ai-services/scripts/cardetect.py
echo "✅ Script moved"

echo "==========================================="
echo "  Step 5 — Commit the reorganization"
echo "==========================================="
git add -A
git commit -m "refactor: move notebooks to ai-services/notebooks/ and scripts to ai-services/scripts/"

echo ""
echo "✅ Done! New layout:"
echo "   ai-services/"
echo "   ├── notebooks/"
echo "   │   ├── car.ipynb"
echo "   │   ├── car_object_detattion.ipynb"
echo "   │   ├── object_detaction.ipynb"
echo "   │   └── yolov11.ipynb"
echo "   └── scripts/"
echo "       └── cardetect.py"
echo ""
echo "Push when ready:  git push origin main"
