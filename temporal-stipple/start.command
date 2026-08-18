#!/bin/sh
# macOS: double-click this file. Linux: run ./start.command from a terminal.
cd "$(dirname "$0")" || exit 1
exec python3 start.py
