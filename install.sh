#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if (( EUID == 0 )); then
  exec python3 manage.py install "$@"
fi
exec sudo python3 "$PWD/manage.py" install --user "$USER" "$@"
