#!/bin/bash
# PAMsim installer for macOS / Linux: installs the libraries and creates a launcher.
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -e ".[gui]"
"$PY" -m pamsim.shortcut
echo "Done - start PAMsim from the Desktop launcher (or: $PY PAMsim.pyw)."
