#!/usr/bin/env bash
# Read-only local inspection. No device/network discovery or control.
set -eu
printf 'Collected (UTC): '
date -u +'%Y-%m-%dT%H:%M:%SZ'
printf '\nKernel and architecture:\n'
uname -srmo
printf '\nOperating system:\n'
if [ -r /etc/os-release ]; then cat /etc/os-release; fi
printf '\nProcessor:\n'
if command -v lscpu >/dev/null 2>&1; then lscpu; fi
printf '\nMemory:\n'
if command -v free >/dev/null 2>&1; then free -h; fi
printf '\nRoot storage:\n'
df -h /
printf '\nPython:\n'
if command -v python3 >/dev/null 2>&1; then python3 --version; else printf 'python3 not found\n'; fi
printf '\nNVIDIA Jetson release (if present):\n'
if [ -r /etc/nv_tegra_release ]; then cat /etc/nv_tegra_release; else printf 'Not present\n'; fi
