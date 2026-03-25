import os
import fitz  # PyMuPDF
from flask import Flask, render_template, request, send_file, jsonify
import io
import traceback

app = Flask(__name__)

# Configurações
ALLOWED_EXTENSIONS = {'pdf'}
# Intervalo de cinza (para detectar o fundo dos campos)
GRAY_TOLERANCE_MIN = (0.80, 0.80, 0.80) 
GRAY_TOLERANCE_MAX = (0.98, 0.98, 0.98) 

# Caminho da fonte
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "Outfit-Regular.ttf")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def compute_effective_color(color, opacity):
    """Calcula a cor visual em um fundo branco, considerando a opacidade."""
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
    """Verifica se a cor é adequada para ser um fundo de campo (tons claros)."""
    if not color:
        return False
    
    # Se a cor for um único float (escala de cinza pura)
    if isinstance(color, (float, int)):
        return 0.75 <= color <= 1.0

    # Se a cor for RGB (tupla de 3)
    if len(color) == 3:
        r, g, b = color
        # Aceita se a média for clara (acima de 0.75) ou se todos componentes forem > 0.75
        threshold = 0.75
        if r > threshold and g > threshold and b > threshold:
            return True
            
        if (r + g + b) / 3 > 0.75:
            return True
            
        return False
    
    return False

def process_pdf(input_stream):
    doc = fitz.open(stream=input_stream, filetype="pdf")
    
    # Tenta carregar a fonte Outfit, se falhar usa a padrão (Helv)
    font_name = "Helv"
    try:
        if os.path.exists(FONT_PATH):
            doc.embfile_add(FONT_PATH, "Outfit", filename=FONT_PATH)
            font_name = "Outfit"
    except Exception:
        print("Aviso: Fonte não carregada, usando padrão.")

    for page in doc:
        paths = page.get_drawings()
        replacements = []

        # 1. Detectar retângulos com fundo claro (campos)
        for path in paths:
            fill = path.get('fill')
            if fill:
                opacity = path.get('fill_opacity', 1.0)
                # IMPORTANTE: Calcula a cor real visualizada (blend com fundo branco)
                effective_color = compute_effective_color(fill, opacity)
                
                if is_field_background(effective_color):
                    # LÓGICA REFINADA:
                    # 1. Filtro de complexidade: Evitar logos, mas permitir retângulos arredondados
                    # - Retângulos simples ('re') = 1 item
                    # - Quadriláteros (4 linhas) = 4 items
                    # - Retângulos arredondados (linhas + curvas) = ~8 items
                    # - Estrela/Polígonos complexos = >10 items
                    
                    items = path.get('items', [])
                    valid_shape = False
                    
                    rect = path['rect']
                    width = rect.width
                    height = rect.height

                    if len(items) == 1 and items[0][0] == 're':
                        valid_shape = True
                    elif len(items) <= 9:
                        # Permite formas simples mistas (linhas e curvas), ex: rounded rects
                        # Verifica se contém apenas linhas e curvas
                        valid_types = {'l', 'c', 're'}
                        current_types = {item[0] for item in items}
                        
                        if current_types.issubset(valid_types):
                            # Se tiver curvas, deve ter linhas também (para evitar círculos/ovais puros que podem ser logos)
                            # Exceção: se for um círculo pequeno (radio button)
                            if 'c' in current_types and 'l' not in current_types:
                                ratio = width / height if height > 0 else 0
                                is_square = 0.8 <= ratio <= 1.2
                                if width < 40 and height < 40 and is_square:
                                    valid_shape = True
                                else:
                                    valid_shape = False
                            else:
                                valid_shape = True

                    if not valid_shape:
                        continue
                    
                    # 2. Filtro de Tamanho: Evitar pequenos artefatos
                    
                    # Lógica de Checkbox existente no código verifica proporção depois.
                    # Vamos permitir passar se for pequeno E quadrado (potencial checkbox)
                    ratio = width / height if height > 0 else 0
                    is_square = 0.8 <= ratio <= 1.2
                    is_potential_checkbox = (width < 40 and height < 40 and is_square)

                    if not is_potential_checkbox:
                        # Se não for checkbox, exige tamanho mínimo de um campo de texto
                        if width < 20 or height < 10:
                            continue

                    # Check if there is existing text in this area
                    if page.get_text("text", clip=rect).strip():
                        continue
                        
                    replacements.append(rect)
                    # "Apaga" o desenho cinza original desenhando um retângulo branco por cima
                    page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), width=0)

        # 2. Criar campos interativos nos locais detectados
        for rect in replacements:
            width = rect.width
            height = rect.height
            
            # Lógica de Classificação
            ratio = width / height if height > 0 else 0
            is_square = 0.8 <= ratio <= 1.2
            is_small = width < 40 and height < 40 
            
            if is_small and is_square:
                # Checkbox
                widget = fitz.Widget()
                widget.rect = rect
                widget.field_name = f"chk_{int(rect.x0)}_{int(rect.y0)}"
                widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
                widget.field_value = False
                widget.field_bgcolor = (0.9, 0.95, 1.0)
                page.add_widget(widget)
            
            elif height > 50:
                # TextArea (Multilinha)
                widget = fitz.Widget()
                widget.rect = rect
                widget.field_name = f"txt_multi_{int(rect.x0)}_{int(rect.y0)}"
                widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                widget.text_font = font_name
                widget.text_fontsize = 10 
                widget.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
                widget.field_bgcolor = (0.9, 0.95, 1.0)
                page.add_widget(widget)
            
            else:
                # Input Normal
                widget = fitz.Widget()
                widget.rect = rect
                widget.field_name = f"input_{int(rect.x0)}_{int(rect.y0)}"
                widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                widget.text_font = font_name
                widget.text_fontsize = max(8, height * 0.6)
                widget.field_bgcolor = (0.9, 0.95, 1.0)
                page.add_widget(widget)

    output_buffer = io.BytesIO()
    doc.save(output_buffer)
    output_buffer.seek(0)
    return output_buffer

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Nenhum arquivo enviado'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'Nome do arquivo vazio'}), 400
            
        if file and allowed_file(file.filename):
            try:
                input_stream = file.read()
                processed_pdf = process_pdf(input_stream)
                
                return send_file(
                    processed_pdf,
                    as_attachment=True,
                    download_name=f"editavel_{file.filename}",
                    mimetype='application/pdf'
                )
            except Exception as e:
                traceback.print_exc()
                return jsonify({'error': f"Erro ao processar PDF: {str(e)}"}), 500
                
        return jsonify({'error': 'Tipo de arquivo inválido'}), 400
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f"Erro no servidor: {str(e)}"}), 500

if __name__ == '__main__':
    # Garante que a pasta templates existe
    if not os.path.exists(os.path.join(BASE_DIR, 'templates')):
        os.makedirs(os.path.join(BASE_DIR, 'templates'))
        print("ALERTA: Pasta 'templates' criada. Mova o index.html para lá!")
        
    app.run(debug=True, port=5000)