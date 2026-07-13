import sys
from pathlib import Path

# Make `observeagents` importable without installation (no packaging in the MVP).
_SDK_ROOT = str(Path(__file__).resolve().parent.parent)
if _SDK_ROOT not in sys.path:
    sys.path.insert(0, _SDK_ROOT)
