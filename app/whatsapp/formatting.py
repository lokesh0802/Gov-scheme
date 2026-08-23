"""
Convert LLM markdown output into clean WhatsApp-friendly text.

WhatsApp supports: *bold*  _italic_  ~strikethrough~  ```monospace```
WhatsApp does NOT support: ### headers  [text](url)  **bold**  - lists with markdown
"""

from __future__ import annotations

import re

# Copied WhatsApp chats, e.g. "[11:18 am, 23/8/2026] Ankitha: hi"
_WHATSAPP_BRACKET_LINE = re.compile(r"^\[\s*[^\]]+\]\s*[^:\n]+:\s*(.*)$")
# Official export lines: "23/8/26, 11:18 am - Ankitha: hi"
_WHATSAPP_DASH_LINE = re.compile(
    r"^\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}(?:\s*[ap]m)?\s*-\s*[^:\n]+:\s*(.*)$",
    re.IGNORECASE,
)


def unwrap_whatsapp_transcript(text: str) -> str:
    """
    If the user pasted a WhatsApp transcript, use the first speaker's line.

    That way a paste like:
      [11:18 am, 23/8/2026] Ankitha: hi
      [11:18 am, 23/8/2026] Dishhh: mil gaya
    is treated as "hi", not as the last line.
    """
    raw = (text or "").strip()
    if not raw:
        return raw

    extracted: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        match = _WHATSAPP_BRACKET_LINE.match(line) or _WHATSAPP_DASH_LINE.match(line)
        if not match:
            return raw
        body = (match.group(1) or "").strip()
        if body:
            extracted.append(body)

    return extracted[0] if extracted else raw


def format_for_whatsapp(text: str) -> str:
    """Clean up text so it reads well in WhatsApp."""
    if not text:
        return text

    t = text

    # Markdown links [Title](url) → Title\n🔗 url
    t = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r"\1\n🔗 \2", t)

    # Bare markdown bold **text** → *text*
    t = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", t)

    # Headers ### 1. Title or ## Title → *1. Title*
    t = re.sub(r"^#{1,6}\s*(\d+\.\s*)?(.+)$", r"*\1\2*", t, flags=re.MULTILINE)

    # Fix double-bold artifacts like *1. *Name** → *1. Name*
    t = re.sub(r"\*(\d+\.)\s*\*([^*]+)\*\*", r"*\1 \2*", t)
    t = re.sub(r"\*\*+", "*", t)

    # Invisible / odd unicode spaces around bullets
    t = t.replace("\u2060", "").replace("\u200b", "").replace("\ufeff", "")

    # "- item" at line start → "• item"
    t = re.sub(r"^-\s+", "• ", t, flags=re.MULTILINE)
    t = re.sub(r"^[•\-\*]\s+", "• ", t, flags=re.MULTILINE)
    t = re.sub(r"^•\s{2,}", "• ", t, flags=re.MULTILINE)

    # Remove markdown code fences
    t = re.sub(r"```\w*\n?", "", t)

    # Label lines like "• *Objective:*" → "• *Objective:*" (already ok)
    t = re.sub(r"\n{3,}", "\n\n", t)

    return t.strip()


def format_scheme_card(
    index: int,
    name: str,
    level: str,
    state: str,
    summary: str,
    url: str,
    benefits: str | None = None,
) -> str:
    """One scheme block — clean WhatsApp layout."""
    lines = [
        f"*{index}. {name}*",
        f"📍 {level} | {state}",
        "",
        summary.strip(),
    ]
    if benefits:
        lines.extend(["", "*Benefits:*", benefits.strip()])
    lines.extend(["", f"🔗 {url}"])
    return "\n".join(lines)


def format_search_list(schemes: list[dict]) -> str:
    """
    schemes: list of dicts with keys name, level, state, summary, url, category (optional)
    """
    if not schemes:
        return ""

    count = len(schemes)
    label = f"{count} scheme(s)" if count != 1 else "1 scheme"
    lines = [f"✅ *Found {label}:*\n"]

    for i, s in enumerate(schemes, 1):
        summary = format_for_whatsapp((s.get("summary") or "").strip())
        if len(summary) > 120:
            summary = summary[:120].rstrip() + "…"

        bullets = [ln.strip() for ln in summary.splitlines() if ln.strip()][:2]
        if bullets:
            detail = "\n".join(
                f"• {ln.lstrip('•').strip()}" if not ln.lstrip().startswith("•") else ln
                for ln in bullets
            )
        elif summary:
            detail = f"• {summary}"
        else:
            detail = "• See official page for details"

        lines.append(
            f"*{i}. {s['name']}*\n"
            f"📍 {s.get('state', 'All India')} | {s.get('level', '')}\n"
            f"{detail}\n"
            f"🔗 {s.get('url', '')}"
        )

    if count <= 4:
        pick = ", ".join(f"*{n}*" for n in range(1, count + 1))
    else:
        pick = "*1*, *2*, *3*, …"
    lines.append(f"\n👆 Reply {pick} for full details.")
    return "\n\n".join(lines)
