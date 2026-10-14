"""Start the PAMsim GUI from a terminal:  python run_gui.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pamsim.gui import main  # noqa: E402

main()
