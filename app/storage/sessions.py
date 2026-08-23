from __future__ import annotations

import json
from pathlib import Path

from app.whatsapp.schemas import WhatsAppSession

SESSIONS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "whatsapp_sessions.json"


def _ensure_store() -> None:
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not SESSIONS_FILE.exists():
        SESSIONS_FILE.write_text("{}", encoding="utf-8")


def _read_all() -> dict[str, dict]:
    _ensure_store()
    return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))


def _write_all(sessions: dict[str, dict]) -> None:
    _ensure_store()
    SESSIONS_FILE.write_text(
        json.dumps(sessions, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def save_session(session: WhatsAppSession) -> WhatsAppSession:
    sessions = _read_all()
    sessions[session.id] = session.model_dump()
    _write_all(sessions)
    return session


def get_session(session_id: str) -> WhatsAppSession | None:
    data = _read_all().get(session_id)
    if not data:
        return None
    return WhatsAppSession.model_validate(data)


def list_sessions() -> list[WhatsAppSession]:
    return [WhatsAppSession.model_validate(data) for data in _read_all().values()]
