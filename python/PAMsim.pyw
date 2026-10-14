"""PAMsim launcher - double-click to start the GUI (no console window)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

if sys.stdout is None or sys.stderr is None:  # started with pythonw: keep a log instead of a console
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    os.makedirs(os.path.join(base, "pamsim"), exist_ok=True)
    log = open(os.path.join(base, "pamsim", "pamsim.log"), "a", buffering=1)
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log

from pamsim.gui import main  # noqa: E402

main()
