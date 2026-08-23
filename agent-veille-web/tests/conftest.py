import sys
from pathlib import Path

# Permet de lancer `pytest` sans installation préalable du package.
SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
