# The conf.py of a docs folder that has none of its own: the shared settings, as they are.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pbsite import *  # noqa: E402,F401,F403
