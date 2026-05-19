---
name: pdf_layout_translator
description: Translate standard text-layer PDF documents with PyMuPDF span extraction and DeepSeek paragraph-level translation while preserving layout. Use when Codex needs to translate PDF papers, reports, forms, manuals, contracts, or other non-scanned PDFs and keep original text positions, font sizes, and formatting as much as possible.
---

# PDF Layout Translator

Use this skill for standard PDFs that already contain a selectable text layer. It extracts text spans with PyMuPDF, merges them into layout blocks, translates at block/paragraph level with DeepSeek, and refills translated text into the original PDF coordinates.

Do not use this first version for scanned or photographed PDFs. If the tool reports that the PDF has no usable text layer, tell the user OCR translation is needed.

## Tool

Call `translate_pdf_preserve_layout`.

Required:
- `file_path`: server-side PDF path from the uploaded attachment note or a user-provided local path.

Optional:
- `target_language`: default `zh-CN`; use the user's requested target language.
- `source_language`: default `auto`; set only when the user clearly specifies it.

## Workflow

1. Use the PDF path injected by upload handling. If no path is visible, ask the user to upload the PDF again.
2. Call `translate_pdf_preserve_layout` with a concise `_purpose` in the user's language.
3. After the tool returns, summarize completion naturally. Do not paste raw JSON.
4. The frontend will render the returned PDF link as a download/open card.

## Behavior

- Detects whether the PDF has a text layer with PyMuPDF.
- Extracts every text span's content, bbox, font size, color, and approximate alignment.
- Merges spans by PyMuPDF text block/lines, so translation happens at paragraph/block level rather than character level.
- Covers the original text area and writes translated text back into the original bbox.
- If translated text does not fit, the renderer tries wrapping, slight font-size reduction, and limited bbox height expansion.
- The output keeps the original PDF background, vector graphics, images, and page size.
