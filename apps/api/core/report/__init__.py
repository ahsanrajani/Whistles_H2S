"""Executive highlights — a cross-surface "what to act on" list and a designed PDF.

Split out of a single ``core/report.py`` (P0.6): ``priorities`` is the ranked
action list the Overview strip and the PDF share; ``highlights`` bundles it with
headline numbers, the sentiment split, share of voice and the worst branches;
``build_pdf`` renders the two-page report (reportlab only, guarded by
``PDF_OK``). This file re-exports the four public names so ``core.report.<name>``
is unchanged.
"""
from .highlights import highlights
from .pdf import PDF_OK, build_pdf
from .priorities import priorities

__all__ = ["priorities", "highlights", "build_pdf", "PDF_OK"]
