"""Launch the independent order review module from a source checkout."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cyct_report.orders.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
