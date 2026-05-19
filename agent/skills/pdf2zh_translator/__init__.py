"""PyMuPDF layout-preserving PDF translation skill."""

from __future__ import annotations

from pathlib import Path

from agent.skills.base import BaseSkill
from agent.tools.builtin.pdf2zh_translate import TranslatePdfPreserveLayoutTool


class Pdf2zhTranslatorSkill(BaseSkill):
    """Translate standard PDFs with PyMuPDF and DeepSeek while preserving layout."""

    name = "pdf_layout_translator"
    description = (
        "Translate standard text-layer PDF documents with PyMuPDF span extraction and DeepSeek while preserving layout. "
        "Use for PDF papers, reports, forms, manuals, and other non-scanned PDFs when the user asks for document/PDF translation with original formatting."
    )
    skill_md_path = Path(__file__).parent / "SKILL.md"

    def get_tools(self) -> list:
        return [TranslatePdfPreserveLayoutTool()]
