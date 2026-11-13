"""Start Nplay AIM for Windows. Double-click, or: pythonw run.pyw [--background]"""

import sys
from pathlib import Path

here = Path(__file__).resolve().parent
sys.path[:0] = [str(here), str(here.parent / "linux-native")]  # shared core: nplayaim/

from nplayaim_win.app import main  # noqa: E402

sys.exit(main(sys.argv[1:]))
