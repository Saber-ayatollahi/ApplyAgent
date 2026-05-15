#!/usr/bin/env bash
# Install ApplyAgent git hooks into .git/hooks/.
# Re-running is safe: existing hook is overwritten with the canonical copy.

set -eu

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "${REPO_ROOT}" ]; then
  echo "[install-hooks] ERROR: not inside a git repository." >&2
  exit 1
fi

SRC="${REPO_ROOT}/scripts/pre-commit"
DST="${REPO_ROOT}/.git/hooks/pre-commit"

if [ ! -f "${SRC}" ]; then
  echo "[install-hooks] ERROR: source hook not found: ${SRC}" >&2
  exit 1
fi

mkdir -p "${REPO_ROOT}/.git/hooks"

# Plain copy (symlinks are flaky on Windows). Overwrite if present.
cp -f "${SRC}" "${DST}"

# chmod is a no-op on Windows NTFS but harmless; keeps POSIX clean.
chmod +x "${DST}" 2>/dev/null || true

echo "[install-hooks] installed: ${DST}"
echo "[install-hooks] source:    ${SRC}"
echo "[install-hooks] bypass with: git commit --no-verify"
