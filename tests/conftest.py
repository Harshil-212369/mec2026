# conftest.py - lets tests import modules from the repo root
# AI assistance: Claude (Anthropic) generated this file.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
