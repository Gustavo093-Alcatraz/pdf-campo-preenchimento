import fitz

def analyze():
    try:
        doc = fitz.open("repro_test.pdf")
        print(f"Opened debug_last_upload.pdf with {len(doc)} pages.")
    except Exception as e:
        print(f"Could not open file: {e}")
        return

    for page_num, page in enumerate(doc):
        print(f"--- Page {page_num + 1} ---")
        paths = page.get_drawings()
        print(f"Found {len(paths)} drawings.")
        
        for i, path in enumerate(paths):
            fill = path.get('fill')
            if fill:
                rect = path['rect']
                # Calculate average brightness
                if isinstance(fill, (list, tuple)) and len(fill) == 3:
                     avg = sum(fill)/3
                     print(f"Drawing {i}: Fill={fill} (Avg={avg:.3f}) | Rect={rect}")
                else:
                     print(f"Drawing {i}: Fill={fill} | Rect={rect}")

if __name__ == "__main__":
    analyze()
