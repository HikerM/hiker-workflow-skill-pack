#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "未找到 Python 3。请先安装 Python 3。" >&2
  exit 2
fi
exec "$PYTHON" "$ROOT/scripts/install_skill.py" "$@"
