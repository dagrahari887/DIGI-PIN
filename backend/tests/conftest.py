import sys
from pathlib import Path

# Allow `import main`, `import core...` etc. from tests/ when run via
# `pytest` from the backend/ directory (this file's parent).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
