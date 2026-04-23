import fitz
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageFilter
import os
import textwrap

def to_bold_serif(text):
    """Convierte texto a negrita Unicode Serif (estilo 𝐀𝐁𝐂)"""
    normal = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    bold = "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"
    trans = str.maketrans(normal, bold)
    return text.translate(trans)

def autocrop_image(img, threshold=245):
    """Recorta agresivamente lo que no sea 'negro' sufiente, eliminando pseudo-blancos"""
    if img.mode != 'RGBA': img = img.convert('RGBA')
    grayscale = img.convert('L')
    mask = grayscale.point(lambda p: 255 if p < threshold else 0)
    bbox = mask.getbbox()
    if bbox:
        return img.crop(bbox)
    return img

def add_drop_shadow(img, offset=(0, 6), shadow_color=(0, 0, 0, 38)):
    """Añade una sombra suave para el efecto de tarjeta editorial (0.15 opacidad aprox)"""
    shadow_width = img.width + 60
    shadow_height = img.height + 60
    shadow_img = Image.new('RGBA', (shadow_width, shadow_height), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_img)
    left, top = 30 + offset[0], 30 + offset[1]
    shadow_draw.rectangle([left, top, left + img.width, top + img.height], fill=shadow_color)
    shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(radius=10))
    final_img = Image.new('RGBA', shadow_img.size, (0, 0, 0, 0))
    final_img.paste(shadow_img, (0, 0), shadow_img)
    final_img.paste(img, (30, 30), img)
    return final_img

def extract_pdf_data(pdf_path):
    doc = fitz.open(pdf_path)
    page = doc[0]
    blocks = page.get_text("dict")["blocks"]
    extracted_blocks = []
    for b in blocks:
        if b["type"] == 0:
            block_text = []
            is_bold = False
            y_pos = b["bbox"][1]
            for l in b["lines"]:
                line_text = " ".join([s["text"] for s in l["spans"]]).strip()
                if line_text:
                    block_text.append(line_text)
                    if any([bool(s["flags"] & 16) or "bold" in s["font"].lower() or "semibold" in s["font"].lower() for s in l["spans"]]):
                        is_bold = True
            if block_text:
                extracted_blocks.append({"text": " ".join(block_text), "y": y_pos, "is_bold": is_bold, "len": sum(len(t) for t in block_text)})
    doc.close()
    extracted_blocks.sort(key=lambda x: x["y"])
    title_idx = -1
    for i, b in enumerate(extracted_blocks):
        text_lower = b["text"].lower()
        if ("buenos aires" in text_lower or "202" in text_lower or "comunicado" in text_lower) and b["len"] < 60:
            continue
        if (b["is_bold"] and b["len"] > 20) or (b["len"] > 40):
            title_idx = i
            break
    if title_idx == -1 and extracted_blocks: title_idx = 0
    title = extracted_blocks[title_idx]["text"] if title_idx != -1 else ""
    has_visual_title = False
    if title_idx != -1:
        bm = extracted_blocks[title_idx]
        if bm["is_bold"]: has_visual_title = True
    intro_lines = []
    if title_idx != -1:
        for b in extracted_blocks[title_idx+1:]:
            if b["text"].strip(): intro_lines.append(b["text"])
    intro = "\n\n".join(intro_lines)
    return {"title": title, "intro": intro, "has_visual_title": has_visual_title}

def generate_pdf_thumbnail(pdf_path, output_path):
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5))
    pix.save(output_path)
    doc.close()
    return output_path

def create_ig_mockup(data, pdf_thumb_path, assets_dir, output_path):
    # --- CONFIGURACIÓN V3.2 (ESCALADO DINÁMICO) ---
    bg_w = 830   # Ancho pantalla interna
    bg_x = (1080 - bg_w) // 2
    bg_y = 220
    bg_h_total = 1480

    # Padding interno solicitado (5%)
    comm_padding = int(bg_w * 0.05)

    h_header = int(bg_h_total * 0.10)
    h_title = int(bg_h_total * 0.15)

    show_title = not data.get("has_visual_title", False)
    if not show_title:
        h_title = 0

    # 1. Fondo + Desenfoque + Overlay
    bg_path = os.path.join(assets_dir, "fondo_bcr_edificio.jpg")
    canvas_orig = Image.open(bg_path).convert("RGBA").resize((1080, 1920), Image.Resampling.LANCZOS)
    canvas = canvas_orig.filter(ImageFilter.GaussianBlur(radius=6))
    overlay = Image.new('RGBA', canvas.size, (0, 10, 30, 100))
    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)

    # 2. Pantalla Interna (Fondo blanco del Tweet)
    draw.rounded_rectangle((bg_x, bg_y, bg_x + bg_w, bg_y + bg_h_total), radius=40, fill=(255, 255, 255, 255))

    font_bold_path = os.path.join(assets_dir, "AdobeGaramondPro-Semibold.otf")
    font_regular_path = os.path.join(assets_dir, "Inter-Regular.ttf")

    if not os.path.exists(font_regular_path):
        font_regular_path = font_bold_path

    # 3. HEADER
    head_y_center = bg_y + (h_header // 2)
    logo_bcr = Image.open(os.path.join(assets_dir, "logo_bcr.png")).convert("RGBA").resize((80, 80), Image.Resampling.LANCZOS)
    canvas.paste(logo_bcr, (bg_x + 25, head_y_center - 40), logo_bcr)

    font_header_bold = ImageFont.truetype(font_bold_path, 30)
    font_handle = ImageFont.truetype(font_regular_path, 22)

    draw.text((bg_x + 120, head_y_center - 32), "Bolsa de Comercio de Rosario", font=font_header_bold, fill=(0, 0, 0))
    draw.text((bg_x + 120, head_y_center + 6), "@BolsaRosario", font=font_handle, fill=(101, 119, 134))

    # 4. TITULO
    title_height_actual = 0
    if show_title:
        title_text = data.get("title", "Comunicado")
        font_size = 36
        title_zone_y = bg_y + h_header
        while font_size > 18:
            font_title = ImageFont.truetype(font_bold_path, font_size)
            title_wrapped = textwrap.fill(title_text, width=int(1400 / font_size))
            if len(title_wrapped.split('\n')) > 3:
                font_size -= 2
                continue
            bbox = draw.multiline_textbbox((0, 0), title_wrapped, font=font_title, spacing=6)
            title_height_actual = bbox[3] - bbox[1]
            if title_height_actual < (h_title - 30):
                break
            font_size -= 2
        draw_title_y = title_zone_y + 20
        draw.multiline_text((bg_x + 25, draw_title_y), title_wrapped, font=font_title, fill=(15, 20, 25), spacing=6)
        title_height_actual += 20

    # 5. COMUNICADO + ESCALADO DINÁMICO
    pdf_thumb = Image.open(pdf_thumb_path).convert("RGBA")
    pdf_thumb = autocrop_image(pdf_thumb, threshold=245)

    comm_y_start = bg_y + h_header + title_height_actual + 15
    bottom_y_limit = bg_y + bg_h_total - 40

    available_h_total = bottom_y_limit - comm_y_start - (comm_padding * 2)
    max_w_comm_box = bg_w - (comm_padding * 2)

    target_h_occupancy = available_h_total * 0.90

    scale_w = max_w_comm_box / pdf_thumb.width
    scale_h = target_h_occupancy / pdf_thumb.height
    scale = min(scale_w, scale_h)

    thumb_w, thumb_h = int(pdf_thumb.width * scale), int(pdf_thumb.height * scale)
    pdf_thumb = pdf_thumb.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)

    card_w, card_h = thumb_w + (comm_padding * 2), thumb_h + (comm_padding * 2)
    white_card = Image.new('RGBA', (card_w, card_h), (255, 255, 255, 255))
    mask_card = Image.new('L', (card_w, card_h), 0)
    ImageDraw.Draw(mask_card).rounded_rectangle((0, 0, card_w, card_h), radius=20, fill=255)
    white_card.putalpha(mask_card)

    white_card.paste(pdf_thumb, (comm_padding, comm_padding), pdf_thumb)

    card_with_shadow = add_drop_shadow(white_card, offset=(0, 8), shadow_color=(0, 0, 0, 38))

    paste_x = bg_x + (bg_w - card_with_shadow.width) // 2
    paste_y = comm_y_start - 30

    canvas.paste(card_with_shadow, (paste_x, paste_y), card_with_shadow)

    # 6. CAPA FINAL: MARCO CELULAR
    marco = Image.open(os.path.join(assets_dir, "marco_celular.png")).convert("RGBA").resize((1080, 1920), Image.Resampling.LANCZOS)
    canvas.paste(marco, (0, 0), marco)

    canvas.convert("RGB").save(output_path, "JPEG", quality=95)
    return output_path