#!/usr/bin/env bash
# Lanzador del imageWatcher.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
exec python3 -m imagewatcher "$@"
