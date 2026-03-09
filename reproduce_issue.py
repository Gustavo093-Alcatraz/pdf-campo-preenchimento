
import fitz
import io

# Copied from app.py for testing
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

def create_test_pdf():
    doc = fitz.open()
    page = doc.new_page()
    
    # 1. Standard Field (Rectangle) - Light Gray
    rect1 = fitz.Rect(50, 50, 200, 80)
    page.draw_rect(rect1, color=(0.9, 0.9, 0.9), fill=(0.9, 0.9, 0.9))
    
    # 2. Logo-like shape (Complex polygon) - Light Gray
    # A star shape or zig-zag
    points = [
        fitz.Point(300, 50), fitz.Point(320, 100), fitz.Point(350, 60), 
        fitz.Point(330, 110), fitz.Point(360, 130), fitz.Point(330, 130), 
        fitz.Point(320, 160), fitz.Point(310, 130), fitz.Point(280, 130), 
        fitz.Point(310, 110)
    ]
    # Draw polygon manually using lines
    shape = page.new_shape()
    for i in range(len(points)):
        p1 = points[i]
        p2 = points[(i + 1) % len(points)]
        shape.draw_line(p1, p2)
    shape.finish(color=(0.9, 0.9, 0.9), fill=(0.9, 0.9, 0.9))
    shape.commit()

    # 3. Another Logo-like shape (Curves/Circle)
    rect3 = fitz.Rect(50, 200, 150, 250)
    page.draw_oval(rect3, color=(0.9, 0.9, 0.9), fill=(0.9, 0.9, 0.9))
    
    return doc

def test_detection():
    doc = create_test_pdf()
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
