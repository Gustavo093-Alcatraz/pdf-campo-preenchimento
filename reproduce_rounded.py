
import fitz
import io

# Copied from app.py
def compute_effective_color(color, opacity):
    if opacity is None:
        opacity = 1.0
    if isinstance(color, (float, int)):
        return color * opacity + (1 - opacity)
    if len(color) == 3:
        r, g, b = color
        return (
            r * opacity + (1 - opacity),
            g * opacity + (1 - opacity),
            b * opacity + (1 - opacity)
        )
    return color

def is_field_background(color):
    if not color:
        return False
    if isinstance(color, (float, int)):
        return 0.75 <= color <= 1.0
    if len(color) == 3:
        r, g, b = color
        threshold = 0.75
        if r > threshold and g > threshold and b > threshold:
            return True
        if (r + g + b) / 3 > 0.75:
            return True
        return False
    return False

def create_rounded_pdf():
    doc = fitz.open()
    page = doc.new_page()
    
    # 1. Standard Field (Rectangle) - Should be detected
    rect1 = fitz.Rect(50, 50, 200, 80)
    page.draw_rect(rect1, color=(0.9, 0.9, 0.9), fill=(0.9, 0.9, 0.9))
    
    # 2. Rounded Rectangle (Standard field in modern design) - Should be detected but might fail current logic
    # Simulated rounded rect path
    rect2 = fitz.Rect(50, 150, 200, 200)
    # Using PyMuPDF's utility can draw it properly but get_drawings will show lines and curves
    # To truly simulate, we need to draw path manually
    shape = page.new_shape()
    
    # Top line
    p1 = fitz.Point(60, 150)
    p2 = fitz.Point(190, 150)
    shape.draw_line(p1, p2)
    # Top-right corner (curve)
    shape.draw_curve(p2, fitz.Point(200, 150), fitz.Point(200, 160)) # Not exact bezier but generates 'c'
    # Right line
    shape.draw_line(fitz.Point(200, 160), fitz.Point(200, 190))
    # Bottom-right corner
    shape.draw_curve(fitz.Point(200, 190), fitz.Point(200, 200), fitz.Point(190, 200))
    # Bottom line
    shape.draw_line(fitz.Point(190, 200), fitz.Point(60, 200))
    # Bottom-left corner
    shape.draw_curve(fitz.Point(60, 200), fitz.Point(50, 200), fitz.Point(50, 190))
    # Left line
    shape.draw_line(fitz.Point(50, 190), fitz.Point(50, 160))
    # Top-left corner
    shape.draw_curve(fitz.Point(50, 160), fitz.Point(50, 150), fitz.Point(60, 150))
    
    shape.finish(color=(0.9, 0.9, 0.9), fill=(0.9, 0.9, 0.9))
    shape.commit()

    return doc

def test_detection():
    doc = create_rounded_pdf()
    page = doc[0]
    paths = page.get_drawings()
    
    print(f"Total paths found: {len(paths)}")
    
    detected_count = 0
    for i, path in enumerate(paths):
        fill = path.get('fill')
        if fill:
            opacity = path.get('fill_opacity', 1.0)
            effective_color = compute_effective_color(fill, opacity)
            
            if is_field_background(effective_color):
                items = path.get('items', [])
                valid_shape = False
                
                if len(items) == 1 and items[0][0] == 're':
                    valid_shape = True
                elif len(items) <= 9:
                    valid_types = {'l', 'c', 're'}
                    current_types = {item[0] for item in items}
                    
                    if current_types.issubset(valid_types):
                        if 'c' in current_types and 'l' not in current_types:
                            valid_shape = False
                        else:
                            valid_shape = True

                if not valid_shape:
                    print(f"Path {i}: Type='{path['type']}', Items={len(path['items'])}, Rect={path['rect']}")
                    print(f"  -> SKIPPED (Complex/Rounded/Curve-only)")
                    item_types = [item[0] for item in items]
                    print(f"     Item Types: {item_types}")
                    continue

                rect = path['rect']
                width = rect.width
                height = rect.height
                ratio = width / height if height > 0 else 0
                is_square = 0.8 <= ratio <= 1.2
                is_potential_checkbox = (width < 30 and height < 30 and is_square)

                if not is_potential_checkbox:
                    if width < 20 or height < 10:
                        print(f"Path {i}: Skipped due to size {width}x{height}")
                        continue
                        
                print(f"Path {i}: Type='{path['type']}', Items={len(path['items'])}, Rect={path['rect']}")
                print(f"  -> DETECTED as field.")
                detected_count += 1

    print(f"Detected {detected_count} potential fields.")

if __name__ == "__main__":
    test_detection()
