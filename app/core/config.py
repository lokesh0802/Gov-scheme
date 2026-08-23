import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """All environment-driven settings in one place."""

    openwa_base_url: str
    openwa_api_key: str
    session_id: str
    session_name: str
    session_secret: str
    bot_phone_number: str
    webhook_url: str
    # RAG / LLM
    openai_api_key: str
    openai_model: str
    openai_embedding_model: str
    schemes_csv_path: Path
    chroma_persist_path: Path
    chroma_collection_name: str
    rag_top_k: int
    embedding_batch_size: int
    rebuild_index_on_startup: bool
    build_index_if_missing: bool

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            openwa_base_url=os.getenv("OPENWA_BASE_URL", "http://localhost:2785").rstrip("/"),
            openwa_api_key=os.getenv("WHATSAPP_HEADERS_X_API_KEY", ""),
            session_id=os.getenv("SESSION_DETAILS_SESSION_ID", ""),
            session_name=os.getenv("SESSION_DETAILS_SESSION_NAME", ""),
            session_secret=os.getenv("SESSION_DETAILS_SECRET", ""),
            bot_phone_number=os.getenv("BOT_PHONE_NUMBER", "8901975539"),
            webhook_url=os.getenv("WEBHOOK_URL", "http://127.0.0.1:8000/webhook"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            openai_embedding_model=os.getenv(
                "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
            ),
            schemes_csv_path=Path(
                os.getenv("SCHEMES_CSV_PATH", str(_PROJECT_ROOT / "web-scraping" / "4000_data.csv"))
            ),
            chroma_persist_path=Path(
                os.getenv("CHROMA_PERSIST_PATH", str(_PROJECT_ROOT / "data" / "chroma"))
            ),
            chroma_collection_name=os.getenv("CHROMA_COLLECTION_NAME", "gov_schemes"),
            rag_top_k=int(os.getenv("RAG_TOP_K", "8")),
            embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "64")),
            rebuild_index_on_startup=_env_bool("REBUILD_INDEX_ON_STARTUP", False),
            build_index_if_missing=_env_bool("BUILD_INDEX_IF_MISSING", True),
        )

    def session_path(self, action: str) -> str:
        """Build an OpenWA session API path, e.g. action='messages/send-text'."""
        return f"/api/sessions/{self.session_id}/{action}"

    @property
    def send_text_url(self) -> str:
        return f"{self.openwa_base_url}{self.session_path('messages/send-text')}"

    @property
    def register_webhook_url(self) -> str:
        return f"{self.openwa_base_url}{self.session_path('webhooks')}"


settings = Settings.from_env()
