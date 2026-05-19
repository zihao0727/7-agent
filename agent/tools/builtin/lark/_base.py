from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from backend.lark_service import get_lark_account

from ...base import BaseTool, ToolExecutionError

USER_IDENTITY_DOMAINS = {"calendar", "contact", "mail", "minutes", "task", "vc"}


DOC_REF_KEYS = {
    "url",
    "doc_url",
    "document_url",
    "documentUrl",
    "token",
    "document_token",
    "documentToken",
    "document_id",
    "documentId",
    "obj_token",
    "objToken",
}

DOC_REF_KEY_PRIORITY = (
    "url",
    "doc_url",
    "document_url",
    "documentUrl",
    "token",
    "document_token",
    "documentToken",
    "obj_token",
    "objToken",
    "document_id",
    "documentId",
)


def _iter_doc_ref_candidates(payload: Any) -> Iterable[str]:
    if isinstance(payload, dict):
        for key in DOC_REF_KEY_PRIORITY:
            value = payload.get(key)
            if isinstance(value, str):
                yield value
        for key in ("document", "doc", "data", "result", "file", "obj"):
            if key in payload:
                yield from _iter_doc_ref_candidates(payload[key])
        for value in payload.values():
            if isinstance(value, (dict, list)):
                yield from _iter_doc_ref_candidates(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_doc_ref_candidates(item)


def _extract_doc_ref(payload: dict[str, Any]) -> str:
    doc_ref = (
        payload.get("url")
        or payload.get("doc_url")
        or payload.get("document_url")
        or payload.get("documentUrl")
        or payload.get("token")
        or payload.get("document_token")
        or payload.get("documentToken")
        or payload.get("document_id")
        or payload.get("documentId")
        or payload.get("obj_token")
        or payload.get("objToken")
    )
    if isinstance(doc_ref, str) and doc_ref.strip():
        return doc_ref.strip()
    for candidate in _iter_doc_ref_candidates(payload):
        candidate = candidate.strip()
        if candidate:
            return candidate
    return ""


def _stringify_payload(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


# Markdown syntax / decorative chars that should not count as "real" content tokens.
_MD_NOISE_RE = re.compile(r"[#>*_`~\-=|\[\](){}!:\\/.,;?\"'…—\s]+")
# CJK letter, latin letter, or digit token (>= 3 chars). Picks signal words out of
# both the source markdown and the fetched (markdown / xml / text) representation.
_CONTENT_TOKEN_RE = re.compile(r"[一-鿿]{3,}|[A-Za-z0-9_]{3,}")


def _content_tokens(value: str) -> list[str]:
    if not value:
        return []
    cleaned = _MD_NOISE_RE.sub(" ", value)
    return _CONTENT_TOKEN_RE.findall(cleaned)


def _looks_like_doc_has_content(fetched_data: Any, *, title: str, text: str) -> bool:
    """Verify the fetched document looks like it received our title + text.

    The fetched payload may be markdown, XML, or plain text depending on
    `--doc-format`, and the lark CLI v2 returns XML by default — so naive
    substring matching against the source markdown is unreliable (e.g. "# foo"
    becomes "<h1>foo</h1>", "> note" becomes "<blockquote>"). We extract
    high-signal content tokens (CJK runs / alnum words >= 3 chars) from the
    source and require a majority of the first few to appear in the fetched
    blob, plus the title to appear at least once.
    """
    blob = _stringify_payload(fetched_data)
    if not blob:
        return False

    title_clean = (title or "").strip()
    if title_clean and title_clean not in blob:
        # Title may be wrapped in tags but the literal characters always survive.
        title_tokens = _content_tokens(title_clean)
        if not title_tokens or not all(token in blob for token in title_tokens[:3]):
            return False

    text_tokens = _content_tokens(text or "")
    if not text_tokens:
        # Nothing to verify against — only the title matters; we already checked it.
        return True

    # Probe up to the first 8 distinct content tokens; require >= 60% to be present.
    seen: set[str] = set()
    probes: list[str] = []
    for token in text_tokens:
        if token in seen:
            continue
        seen.add(token)
        probes.append(token)
        if len(probes) >= 8:
            break
    if not probes:
        return True
    hits = sum(1 for token in probes if token in blob)
    return hits * 10 >= len(probes) * 6


def _json_data(result: dict[str, Any]) -> str:
    return json.dumps(result["data"], ensure_ascii=False, indent=2)


class LarkBaseTool(BaseTool):
    """Shared Feishu/Lark account resolution, identity handling, and errors."""

    async def _get_account(self, current_user_id: int | None, account_id: int | None = None):
        if not current_user_id:
            raise ToolExecutionError(
                self.name,
                "Missing current user context; cannot select a Lark account.",
            )
        return await get_lark_account(int(current_user_id), account_id)

    def _resolve_identity(self, identity: str | None = "auto", domain: str | None = None) -> str:
        safe_identity = identity if identity in {"bot", "user", "auto"} else "auto"
        if safe_identity != "auto":
            return safe_identity
        return "user" if domain in USER_IDENTITY_DOMAINS else "bot"

    def _raise_external_error(self, exc: Exception) -> None:
        detail = getattr(exc, "detail", None)
        if detail is not None:
            raise ToolExecutionError(self.name, json.dumps(detail, ensure_ascii=False)) from exc
        raise ToolExecutionError(self.name, str(exc)) from exc
