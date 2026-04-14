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

def are_overlapping(rect1, rect2, threshold=0.8):
    """Verifica se dois retângulos se sobrepõem significativamente."""
    intersect = rect1 & rect2
    if intersect.is_empty:
        return False
    
    area1 = rect1.width * rect1.height
    area2 = rect2.width * rect2.height
    smaller_area = min(area1, area2)
    
    if smaller_area <= 0:
        return False
        
    overlap_pct = intersect.get_area() / smaller_area
    return overlap_pct >= threshold

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
                    
                    rect = path['rect']
                    
                    # Filtro de Tamanho para avaliar se é pequeno (potencial checkbox/radiobutton)
                    width = rect.width
                    height = rect.height
                    
                    ratio = width / height if height > 0 else 0
                    is_square_or_circle = 0.7 <= ratio <= 1.3
                    is_potential_checkbox_or_radio = (width < 30 and height < 30 and is_square_or_circle)

                    items = path.get('items', [])
                    valid_shape = False
                    is_circle = False # Flag para saber se é puramente curva (círculo)
                    
                    if len(items) == 1 and items[0][0] == 're':
                        valid_shape = True
                    elif len(items) <= 9:
                        # Permite formas simples mistas (linhas e curvas), ex: rounded rects
                        valid_types = {'l', 'c', 're'}
                        current_types = {item[0] for item in items}
                        
                        if current_types.issubset(valid_types):
                            # Se tiver curvas sem linhas (círculos puros)
                            if 'c' in current_types and 'l' not in current_types:
                                if is_potential_checkbox_or_radio:
                                    valid_shape = True
                                    is_circle = True
                                else:
                                    valid_shape = False
                            else:
                                valid_shape = True

                    if not valid_shape:
                        continue
                    
                    if not is_potential_checkbox_or_radio:
                        # Se não for checkbox/radio, exige tamanho mínimo de um campo de texto
                        if width < 20 or height < 10:
                            continue

                    # Check if there is existing text in this area
                    if page.get_text("text", clip=rect).strip():
                        continue
                        
                    # Adiciona ao replacements como uma tupla contendo o retângulo e uma flag indicando se é círculo
                    replacements.append((rect, is_circle))

        # 1.5 Deduplicação e Ordenação
        if not replacements:
            continue

        # Deduplicação: Remove retângulos que se sobrepõem muito
        unique_replacements = []
        for r_tuple in replacements:
            r = r_tuple[0]
            is_dup = False
            for existing_tuple in unique_replacements:
                existing = existing_tuple[0]
                if are_overlapping(r, existing):
                    is_dup = True
                    break
            if not is_dup:
                unique_replacements.append(r_tuple)
        
        # Ordenação: Topo para Baixo, Esquerda para Direita
        unique_replacements.sort(key=lambda r_t: (round(r_t[0].y0 / 5) * 5, r_t[0].x0))

        # 1.6 Classificar e Agrupar
        # (Nesta versão otimizada para estabilidade, mantemos os campos como Checkboxes)
        small_fields = []
        text_fields = []
        
        for rect, is_circle in unique_replacements:
            width = rect.width
            height = rect.height
            ratio = width / height if height > 0 else 0
            is_square_or_circle = 0.7 <= ratio <= 1.3
            is_small = width < 30 and height < 30
            
            if is_small and is_square_or_circle:
                small_fields.append((rect, is_circle))
            else:
                text_fields.append((rect, is_circle))

        # 2. Criar campos interativos (Checkboxes estáveis para permitir desmarcar livremente)
        for idx, (rect, is_circle) in enumerate(small_fields):
            # Unificação visual: Se não era círculo, apaga o quadrado e desenha um círculo sem borda
            if not is_circle:
                page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), width=0)
                center_x = rect.x0 + rect.width / 2
                center_y = rect.y0 + rect.height / 2
                radius = min(rect.width, rect.height) / 2
                # Círculo com cor leve e SEM borda ('sem borda' = width=0)
                page.draw_circle((center_x, center_y), radius, color=None, fill=(0.9, 0.9, 0.9), width=0)
            
            # Criamos uma CHECKBOX internamente para garantir 100% que ela possa ser DESMARCADA
            widget = fitz.Widget()
            widget.rect = rect
            widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
            field_name = f"opt_p{page.number}_{idx}_{int(rect.x0)}"
            widget.field_name = field_name
            
            # Esconde a borda original do widget para o visual mais limpo possível
            widget.border_width = 0
            widget.text_font = "ZaDb" 
            widget.button_caption = "l" # Círculo preenchido no ZapfDingbats
            widget.text_fontsize = 0
            
            page.add_widget(widget)

        # 3. Criar campos de texto (Maiores)
        for rect, is_circle in text_fields:
            height = rect.height
            if height > 50:
                # TextArea (Multilinha)
                widget = fitz.Widget()
                widget.rect = rect
                widget.field_name = f"txt_multi_p{page.number}_{int(rect.x0)}_{int(rect.y0)}"
                widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                widget.text_font = font_name
                widget.text_fontsize = 10 
                widget.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
                page.add_widget(widget)
            else:
                # Input Normal
                widget = fitz.Widget()
                widget.rect = rect
                widget.field_name = f"input_p{page.number}_{int(rect.x0)}_{int(rect.y0)}"
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