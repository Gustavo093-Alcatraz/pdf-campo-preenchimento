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

def is_gray(color):
    """Verifica se a cor é um tom de cinza dentro da tolerância."""
    if not color:
        return False
    
    # Se a cor for um único float (escala de cinza pura)
    if isinstance(color, (float, int)):
        return GRAY_TOLERANCE_MIN[0] <= color <= GRAY_TOLERANCE_MAX[0]

    # Se a cor for RGB (tupla de 3)
    if len(color) == 3:
        r, g, b = color
        # Verifica se R, G e B são quase iguais (neutro)
        if not (abs(r - g) < 0.05 and abs(g - b) < 0.05):
            return False
        return (GRAY_TOLERANCE_MIN[0] <= r <= GRAY_TOLERANCE_MAX[0])
    
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

        # 1. Detectar retângulos cinzas
        for path in paths:
            if path.get('fill') and is_gray(path['fill']):
                rect = path['rect']
                
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
            is_small = width < 30 and height < 30 
            
            if is_small and is_square:
                # Checkbox
                widget = fitz.Widget()
                widget.rect = rect
                widget.field_name = f"chk_{int(rect.x0)}_{int(rect.y0)}"
                widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
                widget.field_value = False
                page.add_widget(widget)
            
            elif height > 50:
                # TextArea (Multilinha)
                widget = fitz.Widget()
                widget.rect = rect
                widget.field_name = f"txt_multi_{int(rect.x0)}_{int(rect.y0)}"
                widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                widget.text_font = font_name
                widget.text_fontsize = 10 # Fixed small size for observations 
                widget.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
                page.add_widget(widget)
            
            else:
                # Input Normal
                widget = fitz.Widget()
                widget.rect = rect
                widget.field_name = f"input_{int(rect.x0)}_{int(rect.y0)}"
                widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                widget.text_font = font_name
                widget.text_fontsize = max(8, height * 0.6)
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