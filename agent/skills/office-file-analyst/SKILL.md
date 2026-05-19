---
name: office-file-analyst
description: Use when the user uploads or references Office/data files and asks to analyze, clean, transform, summarize, visualize, or reformat them. Covers Excel/CSV files (.xlsx, .xls, .csv, .tsv) for data profiling, cleaning, statistics, pivots, charts, and generated cleaned workbooks; and Word files (.docx, .doc) for reading, rewriting, typography, paragraph spacing, headings, tables, page layout, and producing a revised document. Trigger on requests to analyze an Excel file, clean spreadsheet data, generate charts or statistics, adjust Word fonts/paragraphs/layout, or make a document look more professional.
---

# Office File Analyst

## Core Rule

Treat the uploaded file as the source of truth. Before answering, locate the server-side file path injected into the user message, inspect the file with code, and base conclusions on the actual workbook or document. If no usable path is present, ask the user to upload the file again or provide a local path.

Use `run_code` for file inspection, analysis, cleaning, charting, and document generation. Always provide a concise user-facing summary plus the absolute path of any generated output file.

Never try to read an entire workbook or document by printing all rows/text into stdout. The code tool returns only a preview to the model, so repeated attempts to print "more complete data" will create a loop. Instead, compute compact summaries, save complete extracted data or cleaned data to output files, and report the file path.

## File Path Signals

Uploaded files are injected into the conversation as text blocks containing a server absolute path. Look for:

- `Excel file`, `spreadsheet`, or `server absolute path` text with a path such as `D:\...\chat_uploads\...\*.xlsx`
- `Word file`, `document`, or `server absolute path` text with a path such as `D:\...\chat_uploads\...\*.docx`
- Direct user-provided local paths ending in `.xlsx`, `.xls`, `.csv`, `.tsv`, `.docx`, or `.doc`

When multiple files are present, name them explicitly and ask only if the user's target is ambiguous.

## Excel And CSV Workflow

1. Inspect the workbook first.
   - List sheets, dimensions, column names, inferred dtypes, missing counts, duplicate counts, sample rows, date-like columns, numeric ranges, and obvious anomalies.
   - For CSV/TSV, detect encoding when needed and read with `pandas`.
   - Print at most a small sample plus summary metrics. Do not print full worksheets.
2. Clarify only when a destructive or subjective cleaning rule is ambiguous.
   - Safe defaults: trim whitespace, normalize empty strings to null, remove exact duplicate rows, parse dates, convert numeric text, standardize column names, and keep an audit sheet.
3. For analysis, compute useful summaries before writing prose.
   - Use descriptive stats, groupby summaries, pivots, correlation checks, outlier lists, and charts when they help the user's question.
4. For cleaned outputs, write a new file instead of overwriting the upload.
   - Save next to the source as `<stem>_cleaned.xlsx`, `<stem>_analysis.xlsx`, or another descriptive suffix.
   - Include sheets such as `cleaned_data`, `summary`, `issues`, and `audit_log` when useful.
5. Report results in plain language.
   - Mention rows/columns processed, major data quality issues, cleaning actions, notable findings, and output file path.
   - If stdout says it was truncated, do not run more code just to print additional rows. Save rows to an `.xlsx` output and summarize the findings.

Use Python libraries in this preference order:

```python
import pandas as pd
from pathlib import Path
from openpyxl import load_workbook
```

For styled workbooks, use `openpyxl` after `pandas.ExcelWriter` to freeze panes, auto-fit widths approximately, bold headers, add filters, and format dates/numbers.

## Word Formatting Workflow

1. Inspect the document structure before editing.
   - Count paragraphs, tables, headings, images if discoverable, and sample current styles.
2. Preserve content unless the user explicitly asks to rewrite or delete text.
3. Make a new `.docx`; never overwrite the original upload.
   - Save next to the source as `<stem>_formatted.docx`, `<stem>_revised.docx`, or another descriptive suffix.
4. Apply professional defaults when the user asks for general formatting or layout optimization.
   - Chinese body font: Microsoft YaHei or SimSun; English body font: Arial or Times New Roman depending document tone.
   - Body size: 10.5pt or 11pt; line spacing: 1.15 or 1.5; paragraph spacing after: 6pt.
   - Headings: clear hierarchy, bold, larger size, consistent spacing before/after.
   - Tables: repeat header row when appropriate, visible borders, readable cell margins, consistent font.
   - Page: A4 by default, moderate margins, consistent header/footer only when requested or already present.
5. For `.doc` files, explain that direct editing may require conversion to `.docx`; use available tools or ask for `.docx` if conversion is unavailable.

Use `python-docx` for `.docx` operations:

```python
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_LINE_SPACING
```

For Chinese font reliability, set both `run.font.name` and the underlying East Asian font (`w:eastAsia`) in OOXML.

## Output Standard

When finished, answer with:

- What was done.
- Key findings or formatting changes.
- Any assumptions or rows skipped.
- The generated file path, if a file was created.
- Where charts/results can be viewed if `run_code` produced charts.

Do not invent file contents. If code fails because a dependency is missing, state the missing package and provide the smallest dependency addition needed.
