"""Layout-preserving PDF translation with PyMuPDF and DeepSeek."""

from __future__ import annotations

import json
import os
import re
import statistics
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pymupdf
from openai import AsyncOpenAI

from backend.config import get_settings

from ..base import BaseTool, ToolExecutionError, ToolSchema

DEFAULT_TIMEOUT = 1800
MAX_TRANSLATION_ITEMS = 40
MAX_TRANSLATION_CHARS = 7000


@dataclass
class TextBlock:
    page_index: int
    bbox: tuple[float, float, float, float]
    text: str
    font_size: float
    color: int
    align: int


def _data_root() -> Path:
    return Path(__file__).resolve().parents[3] / "data"


def _output_root() -> Path:
    root = _data_root() / "generated" / "document_translations"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _public_base_url() -> str:
    return os.environ.get("API_PUBLIC_BASE_URL", "http://localhost:6868").rstrip("/")


def _public_url(path: Path) -> str:
    rel = path.resolve().relative_to((_data_root() / "generated").resolve())
    parts = [quote(part) for part in rel.parts]
    return f"{_public_base_url()}/generated/{'/'.join(parts)}"


def _has_text_layer(doc: pymupdf.Document) -> bool:
    total = 0
    for page in doc[: min(5, doc.page_count)]:
        total += len((page.get_text("text") or "").strip())
    return total >= 30


def _should_translate(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 2:
        return False
    if not re.search(r"[A-Za-z]", stripped):
        return False
    if re.fullmatch(r"[\W\d_.,:/()$%+\-\s]+", stripped):
        return False
    return True


def _span_color_to_rgb(color: int) -> tuple[float, float, float]:
    r = ((color >> 16) & 255) / 255
    g = ((color >> 8) & 255) / 255
    b = (color & 255) / 255
    return (r, g, b)


def _line_text(line: dict[str, Any]) -> str:
    parts: list[str] = []
    prev_x1: float | None = None
    prev_size = 10.0
    for span in line.get("spans", []):
        text = str(span.get("text") or "")
        if not text:
            continue
        bbox = span.get("bbox") or [0, 0, 0, 0]
        x0 = float(bbox[0])
        if prev_x1 is not None and x0 - prev_x1 > prev_size * 0.35:
            parts.append(" ")
        parts.append(text)
        prev_x1 = float(bbox[2])
        prev_size = float(span.get("size") or prev_size)
    return "".join(parts).strip()


def _block_font_size(block: dict[str, Any]) -> float:
    sizes: list[float] = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text = str(span.get("text") or "")
            if text.strip():
                sizes.append(float(span.get("size") or 10.0))
    return statistics.median(sizes) if sizes else 10.0


def _block_color(block: dict[str, Any]) -> int:
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            if str(span.get("text") or "").strip():
                return int(span.get("color") or 0)
    return 0


def _block_align(block: dict[str, Any], page_width: float) -> int:
    bbox = block.get("bbox") or [0, 0, 0, 0]
    x0, _, x1, _ = [float(v) for v in bbox]
    width = max(1.0, x1 - x0)
    center_offset = abs(((x0 + x1) / 2) - (page_width / 2))
    if center_offset < page_width * 0.04 and width < page_width * 0.8:
        return pymupdf.TEXT_ALIGN_CENTER
    return pymupdf.TEXT_ALIGN_LEFT


def _extract_text_blocks(doc: pymupdf.Document) -> list[TextBlock]:
    items: list[TextBlock] = []
    for page_index, page in enumerate(doc):
        data = page.get_text("dict", flags=11)
        for raw_block in data.get("blocks", []):
            if raw_block.get("type") != 0:
                continue
            lines = [_line_text(line) for line in raw_block.get("lines", [])]
            text = "\n".join(line for line in lines if line).strip()
            if not _should_translate(text):
                continue
            bbox = raw_block.get("bbox") or [0, 0, 0, 0]
            rect = pymupdf.Rect(bbox)
            if rect.is_empty or rect.width < 2 or rect.height < 2:
                continue
            items.append(
                TextBlock(
                    page_index=page_index,
                    bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
                    text=text,
                    font_size=_block_font_size(raw_block),
                    color=_block_color(raw_block),
                    align=_block_align(raw_block, page.rect.width),
                )
            )
    return items


def _chunk_blocks(blocks: list[TextBlock]) -> list[list[TextBlock]]:
    chunks: list[list[TextBlock]] = []
    current: list[TextBlock] = []
    current_chars = 0
    for block in blocks:
        n = len(block.text)
        if current and (len(current) >= MAX_TRANSLATION_ITEMS or current_chars + n > MAX_TRANSLATION_CHARS):
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(block)
        current_chars += n
    if current:
        chunks.append(current)
    return chunks


def _target_label(target_language: str) -> str:
    target = (target_language or "zh-CN").lower()
    if target in {"zh", "cn", "chinese", "zh-cn"}:
        return "Simplified Chinese"
    if target in {"zh-tw", "traditional chinese"}:
        return "Traditional Chinese"
    return target_language


def _parse_translation_json(text: str, expected_len: int) -> list[str]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start >= 0 and end > start:
            parsed = json.loads(cleaned[start : end + 1])
        else:
            raise
    if not isinstance(parsed, list) or len(parsed) != expected_len:
        raise ValueError(f"Expected {expected_len} translations, got {type(parsed).__name__}")
    return [str(item).strip() for item in parsed]


async def _translate_blocks(
    blocks: list[TextBlock],
    *,
    source_language: str,
    target_language: str,
) -> list[str]:
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise ToolExecutionError("translate_pdf_preserve_layout", "未配置 DEEPSEEK_API_KEY，无法翻译 PDF。")

    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )
    model = os.environ.get("PDF_TRANSLATION_DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"
    results: list[str] = []
    target_label = _target_label(target_language)
    source_label = source_language if source_language and source_language != "auto" else "auto-detected source language"

    for chunk in _chunk_blocks(blocks):
        payload = [block.text for block in chunk]
        response = await client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional document translation engine. "
                        "Return only a JSON array of translated strings. "
                        "Preserve numbers, field names, punctuation intent, line breaks where useful, and do not add explanations."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Translate each item from {source_label} to {target_label}. "
                        "Keep placeholders, tax form line numbers, dates, and standalone codes unchanged when appropriate. "
                        "Return a JSON array with the same length and order.\n\n"
                        + json.dumps(payload, ensure_ascii=False)
                    ),
                },
            ],
        )
        content = response.choices[0].message.content or "[]"
        try:
            results.extend(_parse_translation_json(content, len(chunk)))
        except Exception as exc:
            raise ToolExecutionError(
                "translate_pdf_preserve_layout",
                f"DeepSeek 返回的翻译结果格式不可解析: {content[:500]}",
            ) from exc
    return results


def _fit_rect(rect: pymupdf.Rect, page_rect: pymupdf.Rect, font_size: float, text: str) -> pymupdf.Rect:
    line_count = max(1, text.count("\n") + 1)
    needed = min(page_rect.height - rect.y0, max(rect.height, line_count * font_size * 1.25))
    extra = min(max(0.0, needed - rect.height), font_size * 3.0)
    return pymupdf.Rect(rect.x0, rect.y0, rect.x1, min(page_rect.y1, rect.y1 + extra))


def _insert_fitted_text(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    text: str,
    *,
    font_size: float,
    color: tuple[float, float, float],
    align: int,
    target_language: str,
) -> dict[str, Any]:
    page_rect = page.rect
    fit_rect = _fit_rect(rect, page_rect, font_size, text)
    fontname = "china-ss" if (target_language or "").lower().startswith("zh") else "helv"
    try:
        page.insert_font(fontname=fontname)
    except Exception:
        fontname = "helv"

    min_size = max(5.0, font_size * 0.72)
    size = min(font_size, 16.0)
    attempts = 0
    while size >= min_size:
        attempts += 1
        remaining = page.insert_textbox(
            fit_rect,
            text,
            fontsize=size,
            fontname=fontname,
            color=color,
            align=align,
            overlay=True,
        )
        if remaining >= 0:
            return {"font_size": round(size, 2), "expanded": round(fit_rect.height - rect.height, 2), "attempts": attempts}
        size -= 0.6

    page.insert_textbox(
        fit_rect,
        text,
        fontsize=min_size,
        fontname=fontname,
        color=color,
        align=align,
        overlay=True,
    )
    return {"font_size": round(min_size, 2), "expanded": round(fit_rect.height - rect.height, 2), "attempts": attempts, "overflow": True}


def _paint_translations(
    doc: pymupdf.Document,
    blocks: list[TextBlock],
    translations: list[str],
    *,
    target_language: str,
) -> dict[str, Any]:
    adjusted = 0
    overflow = 0
    for block, translated in zip(blocks, translations):
        page = doc[block.page_index]
        rect = pymupdf.Rect(block.bbox)
        padded = pymupdf.Rect(rect.x0 - 0.5, rect.y0 - 0.5, rect.x1 + 0.5, rect.y1 + 0.5)
        page.draw_rect(padded, color=None, fill=(1, 1, 1), overlay=True)
        info = _insert_fitted_text(
            page,
            rect,
            translated,
            font_size=block.font_size,
            color=_span_color_to_rgb(block.color),
            align=block.align,
            target_language=target_language,
        )
        if float(info.get("font_size") or block.font_size) < block.font_size:
            adjusted += 1
        if info.get("overflow"):
            overflow += 1
    return {"adjusted_blocks": adjusted, "overflow_blocks": overflow}


class TranslatePdfPreserveLayoutTool(BaseTool):
    """Translate text-layer PDFs with PyMuPDF extraction and coordinate refill."""

    name = "translate_pdf_preserve_layout"
    description = (
        "Translate a standard text-layer PDF using PyMuPDF span extraction and DeepSeek paragraph translation, "
        "then refill translated text into the original coordinates while preserving layout as much as possible."
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute or relative path to a standard text-layer PDF.",
                    },
                    "source_language": {
                        "type": "string",
                        "description": "Source language code. Use auto when unsure.",
                        "default": "auto",
                    },
                    "target_language": {
                        "type": "string",
                        "description": "Target language code, for example zh-CN, en, ja.",
                        "default": "zh-CN",
                    },
                },
                "required": ["file_path"],
            },
        )

    async def execute(
        self,
        file_path: str,
        source_language: str = "auto",
        target_language: str = "zh-CN",
    ) -> str:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise ToolExecutionError(self.name, f"PDF 文件不存在或不是文件: {file_path}")
        if path.suffix.lower() != ".pdf":
            raise ToolExecutionError(self.name, "只支持 .pdf 文件")

        try:
            doc = pymupdf.open(path)
        except Exception as exc:
            raise ToolExecutionError(self.name, f"无法打开 PDF: {exc}") from exc

        if not _has_text_layer(doc):
            doc.close()
            raise ToolExecutionError(self.name, "该 PDF 没有可用文字层，可能是扫描件/拍照件；需要 OCR 翻译流程。")

        blocks = _extract_text_blocks(doc)
        if not blocks:
            doc.close()
            raise ToolExecutionError(self.name, "未提取到可翻译的文本块。")

        translations = await _translate_blocks(
            blocks,
            source_language=source_language,
            target_language=target_language,
        )
        layout_stats = _paint_translations(doc, blocks, translations, target_language=target_language)

        run_id = uuid.uuid4().hex[:12]
        out_dir = _output_root() / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{path.stem}-translated.pdf"
        doc.save(out_path, garbage=4, deflate=True)
        doc.close()

        result = {
            "type": "pdf_translation_result",
            "success": True,
            "message": "PDF 翻译完成",
            "engine": "pymupdf-deepseek",
            "source_file": str(path),
            "target_language": target_language,
            "pages": len({block.page_index for block in blocks}),
            "translated_blocks": len(blocks),
            "layout": layout_stats,
            "presigned_url": _public_url(out_path),
            "cos_key": out_path.name,
            "file_size": out_path.stat().st_size,
            "files": [
                {
                    "name": out_path.name,
                    "file_path": str(out_path.resolve()),
                    "presigned_url": _public_url(out_path),
                    "file_size": out_path.stat().st_size,
                }
            ],
            "warnings": [],
        }
        return json.dumps(result, ensure_ascii=False)


# Backward-compatible class name for imports created by the first implementation.
TranslatePdfWithPdf2zhTool = TranslatePdfPreserveLayoutTool
