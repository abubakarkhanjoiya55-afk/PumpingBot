#!/usr/bin/env bash
# Build SceneCut-Pro-Student.zip for sharing with students
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${ROOT}/releases"
NAME="SceneCut-Pro-Student"
ZIP_PATH="${OUT_DIR}/${NAME}.zip"

mkdir -p "${OUT_DIR}"
rm -f "${ZIP_PATH}"

python3 - <<'PY' "${ROOT}" "${ZIP_PATH}" "${NAME}"
import sys, zipfile
from pathlib import Path

root = Path(sys.argv[1]).resolve()
zip_path = Path(sys.argv[2]).resolve()
name = sys.argv[3]

skip_dirs = {
    "__pycache__", ".venv", "venv", ".git", "output", "_uploads",
    "projects", "releases", "dist", "build", ".pytest_cache", "tests",
}
skip_suffix = {".pyc", ".webp", ".pyo"}

def keep(path: Path) -> bool:
    rel = path.relative_to(root)
    parts = set(rel.parts)
    if parts & skip_dirs:
        return False
    if path.suffix in skip_suffix:
        return False
    return True

count = 0
with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not keep(path):
            continue
        arc = f"{name}/{path.relative_to(root).as_posix()}"
        zf.write(path, arcname=arc)
        count += 1
    # Friendly top-level README alias
    readme = root / "STUDENT_README.txt"
    if readme.exists():
        zf.write(readme, arcname=f"{name}/README.txt")

print(f"Added {count} files")
print(f"Built: {zip_path} ({zip_path.stat().st_size} bytes)")
PY
