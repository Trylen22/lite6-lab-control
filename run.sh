#!/usr/bin/env bash
# Resolve the project folder so the launcher works from any shell directory.
set -eu
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [ ! -x .venv/bin/python ]; then
    echo 'Create .venv and install requirements-deck.txt; see README.md.' >&2
    exit 1
fi
exec .venv/bin/python scripts/run_lab.py
