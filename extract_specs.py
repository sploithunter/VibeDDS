#!/usr/bin/env python3
"""Extract text from DDS spec PDFs and save as markdown files."""

import os
import re
import pymupdf

SPEC_DIR = os.path.dirname(os.path.abspath(__file__))

def clean_text(text: str) -> str:
    """Clean up extracted text for markdown."""
    # Collapse excessive blank lines (3+ -> 2)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    # Remove form feed characters
    text = text.replace('\f', '\n\n---\n\n')
    return text.strip()

def extract_pdf_to_md(pdf_path: str, md_path: str) -> int:
    """Extract text from a PDF and write it as a markdown file. Returns page count."""
    doc = pymupdf.open(pdf_path)
    num_pages = len(doc)

    pdf_name = os.path.basename(pdf_path)
    lines = []
    lines.append(f"# {pdf_name.replace('.pdf', '').replace('-', ' ')}")
    lines.append("")
    lines.append(f"_Extracted from `{pdf_name}`_")
    lines.append("")
    lines.append("---")
    lines.append("")

    for page_num in range(num_pages):
        page = doc[page_num]
        text = page.get_text("text")
        if text.strip():
            lines.append(f"## Page {page_num + 1}")
            lines.append("")
            lines.append(clean_text(text))
            lines.append("")

    doc.close()

    content = "\n".join(lines)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)

    return num_pages

def main():
    pdf_files = sorted(
        f for f in os.listdir(SPEC_DIR)
        if f.endswith('.pdf')
    )

    if not pdf_files:
        print("No PDF files found.")
        return

    # Create specs/ subdirectory for markdown output
    specs_dir = os.path.join(SPEC_DIR, "specs")
    os.makedirs(specs_dir, exist_ok=True)

    print(f"Found {len(pdf_files)} PDF files. Extracting to specs/ directory...\n")

    for pdf_file in pdf_files:
        pdf_path = os.path.join(SPEC_DIR, pdf_file)
        md_name = pdf_file.replace('.pdf', '.md')
        md_path = os.path.join(specs_dir, md_name)

        file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        print(f"  Processing: {pdf_file} ({file_size_mb:.1f} MB)")

        try:
            num_pages = extract_pdf_to_md(pdf_path, md_path)
            md_size_mb = os.path.getsize(md_path) / (1024 * 1024)
            print(f"    -> {md_name} ({num_pages} pages, {md_size_mb:.1f} MB)")
        except Exception as e:
            print(f"    ERROR: {e}")

    print(f"\nDone! Markdown files saved to: {specs_dir}/")

if __name__ == "__main__":
    main()
