import logging

import uvicorn
from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.webhook import router as webhook_router
from app.api.whatsapp import router as whatsapp_router
from app.rag.indexer import ensure_index_loaded

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="WhatsApp Chatbot — Government Schemes")


@app.on_event("startup")
def startup_load_rag_index() -> None:
    """Load or build Chroma index and make sure OpenWA will POST real chats."""
    log = logging.getLogger(__name__)
    try:
        ensure_index_loaded()
    except Exception:
        log.exception(
            "RAG index startup failed — webhook will still work, but search is unavailable"
        )
    try:
        from app.whatsapp.client import ensure_inbound_webhook

        ensure_inbound_webhook()
    except Exception:
        log.exception(
            "OpenWA webhook ensure failed — 'hi' will not arrive until /api/webhooks/register succeeds"
        )


# OpenWA posts events to /webhook (no /api prefix)
app.include_router(webhook_router)
# Your own API for setup and testing
app.include_router(whatsapp_router, prefix="/api")
app.include_router(health_router, prefix="/api")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
