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

    ticket_documents: List[Any] = []
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

    # If only one ticket, simply save and exit early
    if len(ticket_documents) == 1:
        ticket_documents[0].save(str(destination_path))
        return
    
    # For multiple tickets, we need to merge all documents into one
    # Start with the first ticket document as our base/final document
    final_doc = ticket_documents[0]
    target_body = final_doc.element.body
    
    # Extract and store the section properties (page setup, margins, etc.) from the first document
    # This defines the page layout that will be used for all pages in the final document
    base_sect_pr = _detach_body_sectpr(target_body)
    if base_sect_pr is None:
        raise ValueError("Template is missing section properties.")
    
    # Iterate through each subsequent ticket document and append its content to the final document
    for sub_doc in ticket_documents[1:]:
        source_body = sub_doc.element.body
        
        # Remove section properties from the source document to avoid conflicts
        # We'll use our base section properties for consistent page layout
        _detach_body_sectpr(source_body)
        
        # Find the last paragraph in the target document before adding new content
        # This is where we'll insert a section break to start a new page
        last_paragraph = _get_last_paragraph(target_body)
        if last_paragraph is not None:
            # Add a section break with "nextPage" type to the last paragraph
            # This ensures the next ticket content starts on a fresh page
            _add_section_break_to_paragraph(last_paragraph, base_sect_pr)
        
        # Copy all content elements (paragraphs, tables, etc.) from the source document
        # and append them to the target document body
        _append_page_children(target_body, source_body)
    
    # After all tickets are merged, append the final section properties
    # This ensures the last page maintains the correct layout settings
    target_body.append(deepcopy(base_sect_pr))
    
    # Save the complete merged document to the destination path
    final_doc.save(str(destination_path))


def _append_page_children(target_body, source_body) -> None:
    """
    Copy non-section children from ``source_body`` into ``target_body``.
    
    This function iterates through all XML elements in the source document body
    (such as paragraphs, tables, images, etc.) and appends them to the target document.
    Section properties (sectPr) are skipped because we manage page layout separately
    using the base section properties.
    """
    for child in list(source_body):
        # Skip section property elements - we handle page layout with base_sect_pr
        if child.tag.endswith("sectPr"):
            continue
        # Deep copy the element to avoid reference issues, then append to target
        target_body.append(deepcopy(child))


def _replace_placeholders(document: Any, replacements: Mapping[str, str]) -> None:
    for root in _iter_xml_roots(document):
        for placeholder, value in replacements.items():
            _replace_placeholder_in_root(root, placeholder, value)


def _iter_xml_roots(document: Any) -> Iterable[Any]:
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
    """
    Extract and remove section properties from a document body element.
    
    Section properties (sectPr) define page layout settings like margins, size,
    orientation, headers/footers, etc. We need to detach them to prevent conflicts
    when merging multiple documents, then reapply them strategically.
    
    Returns the detached sectPr element, or None if not found.
    """
    # Use XPath to find section properties in the document body
    sect_pr = body.xpath("./w:sectPr")
    if sect_pr:
        element = sect_pr[0]
        # Remove the element from the body but keep a reference to return it
        body.remove(element)
        return element
    return None


def _get_last_paragraph(body: Any) -> Any | None:
    """
    Find the last paragraph element in a document body.
    
    We need to locate the last paragraph so we can insert a section break into it,
    which will force the next content to start on a new page. Word stores section
    breaks as properties within paragraph elements, not as standalone elements.
    
    Returns the last paragraph element, or None if no paragraphs exist.
    """
    children = list(body)
    # Iterate backwards through children to find the last paragraph element
    for child in reversed(children):
        # Paragraph elements have tags ending with "p" (e.g., "{namespace}p")
        if child.tag.endswith("p"):
            return child
    return None


def _add_section_break_to_paragraph(paragraph: Any, base_sect_pr: Any) -> None:
    """
    Add a section break with nextPage type to ensure next content starts on a new page.
    
    In Word's XML structure, section breaks are embedded within paragraph elements.
    By adding section properties with type="nextPage" to the last paragraph of a section,
    we force Word to start the next section (next ticket) on a new page.
    
    Args:
        paragraph: The paragraph element where the section break will be inserted
        base_sect_pr: The base section properties (page layout) to copy and modify
    """
    # Create a deep copy of the base section properties to avoid modifying the original
    sect_pr = deepcopy(base_sect_pr)
    
    # Look for an existing section type element in the section properties
    type_elem = sect_pr.find(qn("w:type"))
    
    # If no type element exists, create one and insert it at the beginning
    if type_elem is None:
        type_elem = OxmlElement("w:type")
        sect_pr.insert(0, type_elem)
    
    # Set the type attribute to "nextPage" which forces a page break
    # Other options would be "continuous" (no break) or "oddPage"/"evenPage"
    type_elem.set(qn("w:val"), "nextPage")
    
    # Append the modified section properties to the paragraph
    # This creates the page break effect before the next content
    paragraph.append(sect_pr)


__all__ = ["PalletDocxPage", "export_pallets_to_docx", "DEFAULT_DOCX_TEMPLATE"]
