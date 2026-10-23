"""Settings loaded from .env at startup (restart the app after editing .env)."""
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY: str | None = os.getenv("GROQ_API_KEY")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
MAX_INPUT_CHARS: int = int(os.getenv("MAX_INPUT_CHARS", "12000"))
