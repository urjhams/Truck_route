"""
Utility helpers for exporting pallet documents based on the bundled Word template.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence, Any, List

from TruckRouteApp.util import resolve_asset_path

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

DEFAULT_DOCX_TEMPLATE = resolve_asset_path("Template.docx")


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
    max_product_chars: int = 80,
    max_address1_chars: int = 50,
) -> None:
    """
    Generate a Word document where each pallet ticket occupies a page based on the template.
    
    TEXT FORMATTING TO MAINTAIN CONSISTENT LAYOUT:
    - Product names longer than max_product_chars are truncated with "..." (max ~2 lines)
    - Address line 1 longer than max_address1_chars is truncated with "..." and comma added
    - This ensures the pallet index line always remains the last visible line on each page
    - Prevents layout breaking when text wraps to 3+ lines
    
    Args:
        destination: Output file path
        pages: Sequence of pallet ticket data
        template_path: Path to the Word template file
        max_product_chars: Maximum characters for product name (default 80, ~2 lines at 12pt font)
        max_address1_chars: Maximum characters for address line 1 (default 50, ~1 line at 12pt font)
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
        
        # Smart text formatting to maintain consistent layout
        address1, address2 = _format_address_lines(
            page.address_line_1,
            page.address_line_2,
            max_address1_chars
        )
        product_name = _truncate_text(page.product_name, max_product_chars)
        
        _replace_placeholders(
            document,
            {
                "<Name>": page.customer_name,
                "<Adress_1>": address1,
                "<Adress_2>": address2,
                "<Address_1>": address1,  # template currently uses the double-d spelling
                "<Address_2>": address2,
                "<ProductName>": product_name,
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
    
    # Remove all empty paragraphs from the first ticket initially
    # We'll add them back strategically for consistent spacing
    _remove_all_empty_paragraphs(target_body)
    
    # Iterate through each subsequent ticket document and append its content to the final document
    for sub_doc in ticket_documents[1:]:
        source_body = sub_doc.element.body
        
        # Remove section properties from the source document to avoid conflicts
        # We'll use our base section properties for consistent page layout
        _detach_body_sectpr(source_body)
        
        # Find the last NON-EMPTY paragraph in the target document before adding new content
        # This is the pallet index line where we'll insert a section break
        last_paragraph = _get_last_paragraph(target_body)
        if last_paragraph is not None:
            # Add an empty paragraph BEFORE adding the section break
            # This provides spacing between pallet index and the section break
            _add_empty_paragraph(target_body)
            
            # Now add the section break to what is now the last paragraph (the empty one)
            # This way the empty spacing is before the break, maintaining consistent layout
            new_last = _get_last_actual_paragraph(target_body)
            if new_last is not None:
                _add_section_break_to_paragraph(new_last, base_sect_pr)
        
        # Copy all content elements from source, but skip empty paragraphs
        # We manage empty paragraphs manually for consistency
        _append_page_children(target_body, source_body, keep_one_empty=False)
    
    # Add one empty paragraph at the end for the last page
    _add_empty_paragraph(target_body)
    
    # Append the final section properties
    # This ensures the last page maintains the correct layout settings
    target_body.append(deepcopy(base_sect_pr))
    
    # Save the complete merged document to the destination path
    final_doc.save(str(destination_path))


def _truncate_text(text: str, max_chars: int) -> str:
    """
    Truncate text to maximum character length, adding ellipsis if truncated.
    
    This ensures long product names don't break the layout by wrapping to 3+ lines.
    Maximum 2 lines means approximately 80-100 characters depending on font size.
    
    Args:
        text: The text to truncate
        max_chars: Maximum character length
        
    Returns:
        Truncated text with "..." appended if it was cut off
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."


def _format_address_lines(
    address1: str,
    address2: str,
    max_address1_chars: int
) -> tuple[str, str]:
    """
    Format address lines to fit within layout constraints while maintaining paragraph structure.
    
    STRATEGY:
    - If address_line_1 is short enough (≤ max_address1_chars), keep them separate on 2 lines
    - If address_line_1 is too long, merge with comma and split intelligently into 2 lines
    - We must populate BOTH address line placeholders since template has 2 separate paragraphs
    
    Examples:
        Short address:
          Line 1: "123 Main St"
          Line 2: "City, State 12345"
        
        Long address (merged and re-split):
          Original: "123 Very Long Street Name Building A" + "Springfield, MA"
          Line 1: "123 Very Long Street Name Building A,"  (street + comma)
          Line 2: "Springfield, MA"  (city stays on line 2)
    
    Args:
        address1: First line of address (street)
        address2: Second line of address (city, state, zip)
        max_address1_chars: Maximum characters for line 1 before merging
        
    Returns:
        Tuple of (formatted_address1, formatted_address2)
    """
    # If address_line_1 is short enough, keep them separate
    if len(address1) <= max_address1_chars:
        return (address1, address2)
    
    # Address_line_1 is too long
    # Strategy: Add comma to address1, keep address2 separate
    # This signals they're connected but maintains the 2-line structure
    # If the full address1 is too long, truncate it
    max_truncated = max_address1_chars - 1  # Reserve space for comma
    if len(address1) > max_truncated:
        address1 = address1[:max_truncated - 3] + "..."
    
    return (address1 + ",", address2)


def _remove_all_empty_paragraphs(body: Any) -> None:
    """
    Remove ALL empty paragraphs from a document body.
    
    Used to clean up the template's empty paragraphs so we can add them
    back strategically for consistent spacing across all pages.
    """
    children_to_remove = []
    for child in list(body):
        if child.tag.endswith("p"):
            text_nodes = child.xpath('.//w:t')
            texts = [n.text for n in text_nodes if n.text]
            combined_text = ''.join(texts).strip()
            
            if not combined_text:
                children_to_remove.append(child)
    
    for child in children_to_remove:
        body.remove(child)


def _get_last_actual_paragraph(body: Any) -> Any | None:
    """
    Get the absolute last paragraph element (including empty ones).
    
    This is different from _get_last_paragraph which skips empty paragraphs.
    Used to find where to add section breaks after adding spacing paragraphs.
    """
    children = list(body)
    for child in reversed(children):
        if child.tag.endswith("p"):
            return child
    return None


def _add_empty_paragraph(body: Any) -> None:
    """
    Add an empty paragraph at the end of the document body.
    
    This is used for the last page to maintain consistent vertical alignment
    with other pages that have section breaks in their last paragraph.
    The empty paragraph provides the same spacing that appears after the
    pallet index line on non-final pages.
    """
    from docx.oxml import OxmlElement
    
    # Create a new paragraph element
    p = OxmlElement("w:p")
    
    # Add it to the body
    body.append(p)


def _append_page_children(target_body, source_body, keep_one_empty: bool = False) -> None:
    """
    Copy non-section children from ``source_body`` into ``target_body``.
    
    This function iterates through all XML elements in the source document body
    (such as paragraphs, tables, images, etc.) and appends them to the target document.
    Section properties (sectPr) are skipped because we manage page layout separately
    using the base section properties.
    
    Args:
        target_body: The destination document body
        source_body: The source document body to copy from
        keep_one_empty: If True, keeps ONE empty paragraph for spacing
    """
    empty_paragraphs_found = []
    
    for child in list(source_body):
        # Skip section property elements - we handle page layout with base_sect_pr
        if child.tag.endswith("sectPr"):
            continue
        
        # Handle empty paragraphs
        if child.tag.endswith("p"):
            # Check if paragraph has any text content
            text_nodes = child.xpath('.//w:t')
            texts = [n.text for n in text_nodes if n.text]
            combined_text = ''.join(texts).strip()
            
            # Track empty paragraphs
            if not combined_text:
                empty_paragraphs_found.append(child)
                continue
        
        # Deep copy the element to avoid reference issues, then append to target
        target_body.append(deepcopy(child))
    
    # If requested, keep ONE empty paragraph for consistent spacing
    if keep_one_empty and empty_paragraphs_found:
        target_body.append(deepcopy(empty_paragraphs_found[0]))


def _replace_placeholders(document: Any, replacements: Mapping[str, str]) -> None:
    for root in _iter_xml_roots(document):
        for placeholder, value in replacements.items():
            _replace_placeholder_in_root(root, placeholder, value)


def _iter_xml_roots(document: Any) -> Iterable[Any]:
    """
    Yield all XML root elements that should be searched for placeholders.
    
    YES, headers and footers ARE processed! This function ensures placeholders
    in headers/footers are replaced along with body content.
    """
    # Main body - where the ticket content lives
    yield document.element.body
    # Headers/footers per section - also searched for placeholders
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
    Find the last NON-EMPTY paragraph element in a document body.
    
    HOW TO FIND END OF CONTENT:
    - Word documents are XML with elements like <p> (paragraph), <tbl> (table), <sectPr> (section)
    - This function iterates BACKWARDS through body children to find the last <p> tag
    - We skip empty paragraphs to ensure the pallet index line is always the last visible line
    
    WHY WE NEED THIS:
    - To insert a section break that forces the next ticket onto a NEW PAGE
    - Section breaks must be INSIDE a paragraph element (as <p><sectPr type="nextPage"/></p>)
    - They cannot exist as standalone elements at the body level (except the final one)
    - By placing the break in the last non-empty paragraph (pallet index line),
      we ensure it's always the last visible content on the page
    
    Returns the last non-empty <p> element, or None if no paragraphs exist in the body.
    """
    children = list(body)
    # Iterate backwards through children to find the last NON-EMPTY paragraph element
    for child in reversed(children):
        # Paragraph elements have tags ending with "p" (e.g., "{namespace}p")
        if child.tag.endswith("p"):
            # Check if paragraph has any text content
            text_nodes = child.xpath('.//w:t')
            texts = [n.text for n in text_nodes if n.text]
            combined_text = ''.join(texts).strip()
            
            # Return the first non-empty paragraph we find (going backwards)
            if combined_text:
                return child
    
    # Fallback: if all paragraphs are empty, return the last one anyway
    for child in reversed(children):
        if child.tag.endswith("p"):
            return child
    
    return None


def _add_section_break_to_paragraph(paragraph: Any, base_sect_pr: Any) -> None:
    """
    HOW TO ADD A NEW PAGE AND START FILLING IT:
    
    This is the KEY function that creates page breaks between tickets!
    
    MECHANISM:
    1. Take the last paragraph of the current ticket (e.g., the empty line at the end)
    2. Insert section properties INSIDE that paragraph element
    3. Set the section type to "nextPage" to force a page break
    
    XML STRUCTURE CREATED:
    <p>
        <pPr>
            <sectPr>
                <type val="nextPage"/>  ← Forces new page
                ... page layout settings (margins, size, etc.) ...
            </sectPr>
        </pPr>
        (paragraph text content)
    </p>
    
    WHAT HAPPENS:
    - When Word renders this, it ends the current section/page at this paragraph
    - The NEXT content (next ticket) automatically starts on a NEW PAGE
    - All page layout settings (margins, size) are preserved from base_sect_pr
    
    Args:
        paragraph: The last paragraph of the current ticket
        base_sect_pr: The base section properties (defines page layout)
    """
    # Create a deep copy of the base section properties to avoid modifying the original
    sect_pr = deepcopy(base_sect_pr)
    
    # Look for an existing section type element in the section properties
    # Use qn if available; fall back safely if it's not.
    type_elem = None
    if qn is not None:
        type_elem = sect_pr.find(qn("w:type"))
    else:
        # Best-effort fallback: try to find any child that ends with "type"
        for child in sect_pr:
            if getattr(child, "tag", "").endswith("type"):
                type_elem = child
                break
    
    # If no type element exists, create one and insert it at the beginning
    if type_elem is None:
        # Import locally to avoid calling a possibly-None global
        from docx.oxml import OxmlElement as _OxmlElement
        
        type_elem = _OxmlElement("w:type")
        sect_pr.insert(0, type_elem)
    
    # Set the type attribute to "nextPage" which forces a page break
    # Use qn if available, otherwise set the attribute with a fallback name
    if qn is not None:
        type_elem.set(qn("w:val"), "nextPage")
    else:
        type_elem.set("w:val", "nextPage")
    
    # Append the modified section properties to the paragraph
    # This creates the page break effect - next content will start on a new page
    paragraph.append(sect_pr)


__all__ = ["PalletDocxPage", "export_pallets_to_docx", "DEFAULT_DOCX_TEMPLATE"]
