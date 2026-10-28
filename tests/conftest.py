import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SVAGA_SCRIPTED_LLM", "1")
os.environ.pop("OPENAI_API_KEY", None)
