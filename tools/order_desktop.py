"""Start the desktop. The portable distribution supplies its own Python runtime."""

import argparse
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from cyct_report.orders.desktop import launch
from cyct_report.orders.store import Store

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    launch(Store(args.data_dir))
