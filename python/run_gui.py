"""Start the pamsim GUI:  python run_gui.py   (works without installing the package)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pamsim.gui import main  # noqa: E402

main()
