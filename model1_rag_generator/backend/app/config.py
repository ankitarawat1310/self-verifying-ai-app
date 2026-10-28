import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]

KNOWLEDGE_BASE_DIR = Path(os.getenv("KNOWLEDGE_BASE_DIR", BACKEND_ROOT / "knowledge_base"))
CHROMA_PERSIST_DIR = Path(os.getenv("CHROMA_PERSIST_DIR", BACKEND_ROOT / "chroma_db"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
