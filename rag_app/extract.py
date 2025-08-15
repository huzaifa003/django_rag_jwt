from pathlib import Path
import fitz  # PyMuPDF

def extract_pdf_pages_as_images(pdf_path: str, out_dir: str, dpi: int = 200, max_pages: int | None = None) -> list[dict]:
    out_dir = Path(out_dir)
    img_dir = out_dir / 'images'
    img_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    records: list[dict] = []

    for page_idx in range(len(doc)):
        if max_pages is not None and page_idx >= max_pages:
            break
        page = doc[page_idx]
        img_name = f"{Path(pdf_path).stem}-page-{page_idx+1}.png"
        img_path = img_dir / img_name
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        pix.save(str(img_path))

        records.append({
            'type': 'page_image',
            'page': page_idx + 1,
            'image_path': str(img_path),
            'source': str(pdf_path),
        })

    return records
