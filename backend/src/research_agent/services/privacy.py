"""Lightweight privacy-preserving text scrubbing.

Strips obvious PII patterns (email addresses, phone numbers, Chinese and US
identification numbers, credit-card-shaped digit runs) from text that will
later be forwarded to a remote model.  This is *not* a substitute for
formal de-identification — it is a best-effort pre-filter that reduces the
accidental leakage surface when academic content happens to contain
instructor or author contact details.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from research_agent.db.models import ConversationSession, Message, utc_now

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_CN = re.compile(r"(?:\+?86[-\s]?)?1[3-9]\d{9}")
_PHONE_INTL = re.compile(r"\+\d{1,3}[\s\-]?\d{4,14}")
_ID_CN = re.compile(r"\b\d{17}[\dXx]\b")  # 18-digit Chinese ID
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CREDIT_CARD = re.compile(r"\b(?:\d[ \-]?){13,16}\d\b")
_URL_WITH_QUERY = re.compile(r"https?://\S+\?\S+")

# Each replacement rule: (pattern, label shown after scrubbing).
# Order matters: more specific patterns (IDs) must run before looser ones
# (phone numbers) so a long ID is not partially scrubbed as a phone.
_RULES: Iterable[tuple[re.Pattern[str], str]] = (
    (_EMAIL, "[email]"),
    (_ID_CN, "[id]"),
    (_SSN, "[ssn]"),
    (_CREDIT_CARD, "[card]"),
    (_URL_WITH_QUERY, "[link]"),
    (_PHONE_CN, "[phone]"),
    (_PHONE_INTL, "[phone]"),
)


def scrub_pii(text: str) -> str:
    """Return *text* with the obvious PII patterns replaced by labels."""
    if not text:
        return text
    for pattern, label in _RULES:
        text = pattern.sub(label, text)
    return text


def scrub_pii_bulk(texts: Iterable[str]) -> list[str]:
    return [scrub_pii(t) for t in texts]


def cleanup_expired_conversations(db: Session, ttl_days: int) -> int:
    """Delete conversations older than the configured retention window."""
    if ttl_days <= 0:
        return 0

    cutoff = utc_now() - timedelta(days=ttl_days)
    session_ids = list(
        db.scalars(
            select(ConversationSession.id).where(
                ConversationSession.created_at < cutoff
            )
        )
    )
    if not session_ids:
        return 0

    db.execute(delete(Message).where(Message.session_id.in_(session_ids)))
    db.execute(
        delete(ConversationSession).where(
            ConversationSession.id.in_(session_ids)
        )
    )
    db.flush()
    return len(session_ids)
