"""Interactive demo for QuestLine.

Run from the repository root:

    python examples/interactive_demo.py
"""

from pathlib import Path
import sys

# Allow running this file directly from examples/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from questline import interactive


if __name__ == "__main__":
    interactive()
