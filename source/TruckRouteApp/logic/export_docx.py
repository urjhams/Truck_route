"""
Utility helpers for exporting pallet documents based on the bundled Word template.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence, Any, List

try:
    from docx import Document  # type: ignore[import-untyped]
    from docx.document import Document as DocumentType  # type: ignore[import-untyped]
    from docx.oxml import OxmlElement  # type: ignore[import-untyped]
    from docx.oxml.ns import qn  # type: ignore[import-untyped]
except ModuleNotFoundError as exc:  # pragma: no cover - dependency optional at runtime
    Document = None  # type: ignore[assignment]
    DocumentType = Any  # type: ignore[assignment]
    OxmlElement = None  # type: ignore[assignment]
    qn = None  # type: ignore[assignment]
    _DOCX_IMPORT_ERROR = exc
else:
    _DOCX_IMPORT_ERROR = None

DEFAULT_DOCX_TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "Template.docx"


@dataclass(slots=True)
class PalletDocxPage:
    """Represents a single pallet ticket that should replace placeholders in the template."""

    customer_name: str
    address_line_1: str
    address_line_2: str
    product_name: str
    pallet_index: int
    pallet_total: int


def export_pallets_to_docx(
    destination: Path | str,
    pages: Sequence[PalletDocxPage],
    *,
    template_path: Path | str = DEFAULT_DOCX_TEMPLATE,
) -> None:
    """
    Generate a Word document where each pallet ticket occupies a page based on the template.
    """
    if Document is None:
        raise ModuleNotFoundError(
            "python-docx is not installed. Install it with 'pip install python-docx' to export DOCX files."
        ) from _DOCX_IMPORT_ERROR
    if not pages:
        raise ValueError("No pallet data to export.")
    template = Path(template_path)
    if not template.exists():
        raise FileNotFoundError(f"Template file '{template}' does not exist.")

    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    ticket_documents: List[DocumentType] = []
    for page in pages:
        document = Document(str(template))
        _replace_placeholders(
            document,
            {
                "<Name>": page.customer_name,
                "<Adress_1>": page.address_line_1,
                "<Adress_2>": page.address_line_2,
                "<Address_1>": page.address_line_1,  # template currently uses the double-d spelling
                "<Address_2>": page.address_line_2,
                "<ProductName>": page.product_name,
                "<X>": str(page.pallet_total),
                "<a>": str(page.pallet_index),
            },
        )
        ticket_documents.append(document)

    final_doc = ticket_documents[0]
    for sub_doc in ticket_documents[1:]:
        _append_page(final_doc, sub_doc)
    final_doc.save(str(destination_path))


def _append_page(target: DocumentType, source: DocumentType) -> None:
    """
    Copy the body content of ``source`` into ``target`` on a new page while keeping the
    template's section properties as the trailing body element.
    """
    target_body = target.element.body
    sect_pr = _detach_body_sectpr(target_body)
    target_body.append(_page_break_paragraph())
    for child in list(source.element.body):
        if child.tag.endswith("sectPr"):
            continue
        target_body.append(deepcopy(child))
    if sect_pr is not None:
        target_body.append(sect_pr)


def _replace_placeholders(document: DocumentType, replacements: Mapping[str, str]) -> None:
    for root in _iter_xml_roots(document):
        for placeholder, value in replacements.items():
            _replace_placeholder_in_root(root, placeholder, value)


def _iter_xml_roots(document: DocumentType) -> Iterable[Any]:
    # Main body
    yield document.element.body
    # Headers/footers per section (if we ever add placeholders there).
    for section in document.sections:
        yield section.header._element  # type: ignore[attr-defined]
        yield section.footer._element  # type: ignore[attr-defined]


def _replace_placeholder_in_root(root, placeholder: str, replacement: str) -> None:
    if not placeholder:
        return
    placeholder_chars = list(placeholder)
    while True:
        char_positions = _collect_char_positions(root)
        start = _find_placeholder_index(char_positions, placeholder_chars)
        if start is None:
            break
        _apply_replacement(char_positions, start, len(placeholder_chars), replacement)


def _collect_char_positions(root: Any) -> list[tuple[Any, int, str]]:
    positions: list[tuple[Any, int, str]] = []
    # Direct XPath avoids having to recurse across Paragraph/Table APIs repeatedly.
    for node in root.xpath(".//w:t"):  # type: ignore[attr-defined]
        text = node.text or ""
        for idx, char in enumerate(text):
            positions.append((node, idx, char))
    return positions


def _find_placeholder_index(
    positions: Sequence[tuple[Any, int, str]],
    needle: Sequence[str],
) -> int | None:
    if not positions or not needle or len(positions) < len(needle):
        return None
    limit = len(positions) - len(needle) + 1
    for start in range(limit):
        for offset, char in enumerate(needle):
            if positions[start + offset][2] != char:
                break
        else:
            return start
    return None


def _apply_replacement(
    positions: Sequence[tuple[Any, int, str]],
    start: int,
    length: int,
    replacement: str,
) -> None:
    affected = positions[start : start + length]
    if not affected:
        return

    node_order: list[Any] = []
    node_indices: dict[Any, list[int]] = {}
    for node, idx, _ in affected:
        node_indices.setdefault(node, []).append(idx)
        if not node_order or node_order[-1] is not node:
            node_order.append(node)

    first_node = node_order[0]
    last_node = node_order[-1]
    for node in node_order:
        indices = node_indices[node]
        first = min(indices)
        last = max(indices)
        text = node.text or ""
        prefix = text[:first]
        suffix = text[last + 1 :]

        if node is first_node and node is last_node:
            node.text = prefix + replacement + suffix
        elif node is first_node:
            node.text = prefix + replacement
        elif node is last_node:
            node.text = suffix
        else:
            node.text = prefix  # usually empty, but keep anything preceding the placeholder segment


def _detach_body_sectpr(body) -> Any | None:
    sect_pr = body.xpath("./w:sectPr")
    if sect_pr:
        element = sect_pr[0]
        body.remove(element)
        return element
    return None


def _page_break_paragraph():
    if OxmlElement is None or qn is None:
        raise ModuleNotFoundError(
            "python-docx is not installed. Install it with 'pip install python-docx' to export DOCX files."
        ) from _DOCX_IMPORT_ERROR
    paragraph = OxmlElement("w:p")
    run = OxmlElement("w:r")
    br = OxmlElement("w:br")
    br.set(qn("w:type"), "page")
    run.append(br)
    paragraph.append(run)
    return paragraph


__all__ = ["PalletDocxPage", "export_pallets_to_docx", "DEFAULT_DOCX_TEMPLATE"]
