"""
将 useChat 随消息发送的 experimental_attachments（data URL）落盘/处理：
- Word (.doc/.docx): 落盘，注入服务器绝对路径，供 convert_word_to_pdf 等工具使用
- PDF (.pdf):        提取文本内容注入消息（同时落盘备份）；调用 Kimi Files API 时质量更高
- TXT (text/plain):  直接读取文本内容注入消息
- 图片 (image/*):   保留在 experimental_attachments 中，由 message_converter 按模型处理（vision）
- 其他:              保留附件，添加类型说明
"""

from __future__ import annotations

import base64
import io
import logging
import uuid
from pathlib import Path
from typing import Any

from backend.model_routing import is_kimi_route

logger = logging.getLogger(__name__)

MAX_BYTES = 32 * 1024 * 1024  # 32 MB

_WORD_SUFFIX = frozenset({".doc", ".docx"})
_WORD_MIME = frozenset(
    {
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)
_IMAGE_MIME_PREFIX = "image/"
_IMAGE_SUFFIX = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"})


# ── 工具函数 ────────────────────────────────────────────────────────────────

def _upload_dir() -> Path:
    root = Path(__file__).resolve().parent.parent / "data" / "chat_uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _parse_data_url(url: str) -> tuple[str, bytes] | None:
    if not url.startswith("data:"):
        return None
    try:
        comma = url.index(",")
    except ValueError:
        return None
    meta = url[5:comma]
    payload = url[comma + 1:]
    is_b64 = ";base64" in meta.lower()
    mime = meta.split(";")[0].strip().lower() or "application/octet-stream"
    raw = base64.b64decode(payload, validate=False) if is_b64 else payload.encode("utf-8")
    return mime, raw


def _effective_mime(name: str | None, mime: str | None, content_type: str | None) -> str:
    ct = (content_type or mime or "").strip().lower()
    if ct:
        return ct
    if name:
        suf = Path(name).suffix.lower()
        if suf in _WORD_SUFFIX:
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if suf == ".pdf":
            return "application/pdf"
        if suf in {".txt", ".text"}:
            return "text/plain"
        if suf in _IMAGE_SUFFIX:
            return f"image/{suf.lstrip('.')}"
    return "application/octet-stream"


def _is_word(name: str | None, mime: str) -> bool:
    if name and Path(name).suffix.lower() in _WORD_SUFFIX:
        return True
    return mime in _WORD_MIME


def _is_pdf(name: str | None, mime: str) -> bool:
    if name and Path(name).suffix.lower() == ".pdf":
        return True
    return mime == "application/pdf"


def _is_txt(name: str | None, mime: str) -> bool:
    if name and Path(name).suffix.lower() in {".txt", ".text", ".csv", ".md", ".log"}:
        return True
    return mime.startswith("text/") and "html" not in mime


def _is_image(name: str | None, mime: str) -> bool:
    if name and Path(name).suffix.lower() in _IMAGE_SUFFIX:
        return True
    return mime.startswith(_IMAGE_MIME_PREFIX)


def _suffix_for_word(name: str | None, mime: str) -> str:
    if name:
        s = Path(name).suffix.lower()
        if s in _WORD_SUFFIX:
            return s
    return ".docx" if "wordprocessingml" in mime else ".doc"


# ── PDF 文本提取 ────────────────────────────────────────────────────────────

def _extract_pdf_text(raw: bytes, filename: str | None = None) -> str:
    """使用 pypdf 提取 PDF 纯文本；失败时返回空字符串。"""
    try:
        import pypdf  # type: ignore
        reader = pypdf.PdfReader(io.BytesIO(raw))
        pages: list[str] = []
        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(f"--- 第 {i + 1} 页 ---\n{text.strip()}")
            except Exception as exc:
                logger.debug("PDF 页面 %d 提取失败: %s", i + 1, exc)
        return "\n\n".join(pages)
    except ImportError:
        logger.warning("pypdf 未安装，无法提取 PDF 文本")
        return ""
    except Exception as exc:
        logger.warning("PDF 文本提取失败 (%s): %s", filename or "未命名", exc)
        return ""


# ── TXT 文本读取 ────────────────────────────────────────────────────────────

def _read_txt_text(raw: bytes, filename: str | None = None) -> str:
    """尝试 UTF-8 / GBK 解码文本文件。"""
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1", errors="replace")


# ── Kimi Files API ──────────────────────────────────────────────────────────

async def _kimi_extract_file_text(
    raw: bytes,
    filename: str,
    mime: str,
) -> str | None:
    """
    调用 Moonshot Files API 上传文件并获取提取文本。
    返回提取到的文本，若失败返回 None（将回退到本地提取）。
    """
    try:
        import httpx
        from backend.config import get_settings
        s = get_settings()
        if not s.kimi_api_key:
            return None

        async with httpx.AsyncClient(timeout=60) as client:
            # 上传文件
            upload_resp = await client.post(
                f"{s.kimi_base_url}/files",
                headers={"Authorization": f"Bearer {s.kimi_api_key}"},
                files={
                    "file": (filename, raw, mime),
                    "purpose": (None, "file-extract"),
                },
            )
            if upload_resp.status_code != 200:
                logger.warning("Kimi 文件上传失败: %s %s", upload_resp.status_code, upload_resp.text[:200])
                return None

            file_id = upload_resp.json().get("id")
            if not file_id:
                return None

            # 获取提取内容
            content_resp = await client.get(
                f"{s.kimi_base_url}/files/{file_id}/content",
                headers={"Authorization": f"Bearer {s.kimi_api_key}"},
            )

            # 清理：删除已上传的文件
            try:
                await client.delete(
                    f"{s.kimi_base_url}/files/{file_id}",
                    headers={"Authorization": f"Bearer {s.kimi_api_key}"},
                )
            except Exception:
                pass

            if content_resp.status_code == 200:
                return content_resp.text
            return None
    except Exception as exc:
        logger.warning("Kimi Files API 调用失败: %s", exc)
        return None


# ── 主处理函数 ──────────────────────────────────────────────────────────────

async def materialize_chat_uploads(
    messages: list[dict[str, Any]],
    model: str = "deepseek-v4-flash",
) -> list[dict[str, Any]]:
    """
    返回新消息列表：
    - Word → 落盘，注入服务器路径
    - PDF  → 提取文本注入（Kimi 用 Files API；DeepSeek 用 pypdf 本地提取）
    - TXT  → 读取文本注入
    - 图片 → 保留在 experimental_attachments，message_converter 后续处理 vision
    - 其他 → 保留附件 + 说明注释
    """
    out: list[dict[str, Any]] = []
    upload_dir = _upload_dir()
    use_kimi = is_kimi_route(model)

    for msg in messages:
        if msg.get("role") != "user":
            out.append(msg)
            continue

        new_msg = dict(msg)
        atts = list(new_msg.pop("experimental_attachments", None) or [])
        additions: list[str] = []
        kept_atts: list[dict[str, Any]] = []

        for att in atts:
            url = att.get("url") or ""
            name: str | None = att.get("name")
            content_type = (att.get("contentType") or att.get("content_type") or "").strip()

            parsed = _parse_data_url(url) if url.startswith("data:") else None
            if not parsed:
                # 非 data URL，保留（例如远程 URL）
                kept_atts.append(att)
                continue

            mime, raw = parsed
            eff_mime = _effective_mime(name, mime, content_type)

            if len(raw) > MAX_BYTES:
                additions.append(
                    f"[附件过大已忽略（>{MAX_BYTES // (1024 * 1024)}MB）]: {name or '未命名'}"
                )
                continue

            # ── Word ────────────────────────────────────────────────────────
            if _is_word(name, eff_mime):
                suf = _suffix_for_word(name, eff_mime)
                safe_name = f"{uuid.uuid4().hex}{suf}"
                dest = upload_dir / safe_name
                try:
                    dest.write_bytes(raw)
                    abs_path = str(dest.resolve())
                    additions.append(
                        f"[已上传 Word 文件，服务器绝对路径（请用 convert_word_to_pdf 的 file_path）]: {abs_path}"
                    )
                    logger.info("Word 已落盘: %s (来自: %s)", abs_path, name)
                except OSError as exc:
                    logger.warning("Word 落盘失败: %s", exc)
                    additions.append(f"[保存 Word 文件失败]: {name or '未命名'} — {exc}")
                continue

            # ── PDF ─────────────────────────────────────────────────────────
            if _is_pdf(name, eff_mime):
                # 落盘备份
                safe_name = f"{uuid.uuid4().hex}.pdf"
                dest = upload_dir / safe_name
                try:
                    dest.write_bytes(raw)
                    logger.info("PDF 已落盘: %s (来自: %s)", dest, name)
                except OSError as exc:
                    logger.warning("PDF 落盘失败: %s", exc)

                # 提取文本
                text_content: str | None = None
                if use_kimi:
                    fn = name or "document.pdf"
                    text_content = await _kimi_extract_file_text(raw, fn, "application/pdf")
                    if text_content:
                        logger.info("Kimi Files API 提取 PDF 文本成功: %s 字符", len(text_content))

                if not text_content:
                    text_content = _extract_pdf_text(raw, name)
                    if text_content:
                        logger.info("pypdf 提取 PDF 文本: %s 字符", len(text_content))

                if text_content and text_content.strip():
                    label = name or "document.pdf"
                    additions.append(
                        f"[PDF 文件内容 - {label}]\n{text_content.strip()}"
                    )
                else:
                    additions.append(
                        f"[PDF 文件已上传，但未能提取到文本内容]: {name or '未命名'}"
                    )
                continue

            # ── TXT / 纯文本 ─────────────────────────────────────────────────
            if _is_txt(name, eff_mime):
                text_content = _read_txt_text(raw, name)
                label = name or "text_file.txt"
                additions.append(
                    f"[文本文件内容 - {label}]\n{text_content}"
                )
                logger.info("TXT 已读取: %s 字符 (来自: %s)", len(text_content), name)
                continue

            # ── 图片：保留 experimental_attachments，由 message_converter 处理 vision ──
            if _is_image(name, eff_mime):
                kept_atts.append(att)
                logger.debug("图片保留在 attachments: %s (%s)", name, eff_mime)
                continue

            # ── 其他未知类型 ────────────────────────────────────────────────
            kept_atts.append(att)
            additions.append(
                f"[附件已附加（类型: {eff_mime}）]: {name or '未命名'}"
            )

        if kept_atts:
            new_msg["experimental_attachments"] = kept_atts

        if additions:
            block = "\n\n".join(additions)
            content = new_msg.get("content", "")
            if isinstance(content, str):
                new_msg["content"] = (content + "\n\n" if content else "") + block
            elif isinstance(content, list):
                parts = list(content)
                parts.append({"type": "text", "text": block})
                new_msg["content"] = parts
            else:
                new_msg["content"] = block

        out.append(new_msg)

    return out
