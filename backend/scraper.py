import requests
from bs4 import BeautifulSoup
import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from moviepy.video.io.ImageSequenceClip import ImageSequenceClip
from moviepy.video.io.VideoFileClip import VideoFileClip
from datetime import datetime

# Rutas relativas para portabilidad (Render/GitHub)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
STATIC_DIR = os.path.join(BASE_DIR, "static")
FONT_PATH = os.path.join(ASSETS_DIR, "Adobe Garamond Pro Semibold.otf")

def get_day_labels():
    is_monday = datetime.now().weekday() == 0
    if is_monday:
        return {
            "tweet_header": "🌧️ Les compartimos las lluvias acumuladas en la región núcleo durante las últimas 72 horas, registradas desde el viernes a las 8 AM hasta hoy a las 8 AM:",
            "video_subtitle": "Mayores registros de las últimas 72 h"
        }
    else:
        return {
            "tweet_header": "🌧️ Les compartimos las lluvias acumuladas en la región núcleo durante las últimas 24 horas, registradas desde ayer a las 8 AM hasta hoy a las 8 AM:",
            "video_subtitle": "Mayores registros de las últimas 24 h"
        }

def ensure_font(size=30):
    try:
        if os.path.exists(FONT_PATH):
            return ImageFont.truetype(FONT_PATH, size)
        return ImageFont.load_default()
    except:
        return ImageFont.load_default()

def create_animated_video_from_data(top_5, map_path, output_mp4=None):
    if output_mp4 is None:
        output_mp4 = os.path.join(STATIC_DIR, "historia_lluvias.mp4")
        
    # --- OPTIMIZACIÓN DE MEMORIA (v2.1) ---
    # Bajamos resolución a 540x960 (consume 4 veces menos RAM que 1080p)
    W, H = 540, 960
    FPS = 10 # Bajamos levemente el FPS para mayor estabilidad
    
    # Ajustamos tamaños de fuente para la nueva resolución
    font_title = ensure_font(38)
    font_subtitle = ensure_font(28)
    font_items = ensure_font(32)
    font_footer = ensure_font(22)

    bg_video_path = os.path.join(STATIC_DIR, "background_rain.mp4")
    
    # Si falta el video de fondo, vamos al modo simple
    if not os.path.exists(bg_video_path):
        return create_animated_video_legacy(top_5, map_path, output_mp4)
    
    bg_clip = VideoFileClip(bg_video_path)
    # Redimensionamos el video de fondo a la nueva escala reducida
    bg_clip = bg_clip.resized(height=H) 
    bg_clip = bg_clip.cropped(x_center=bg_clip.size[0]/2, width=W)
    
    DURATION = min(bg_clip.duration, 8) # Recortamos duración a 8 segundos
    
    # Cargamos el mapa una sola vez y lo redimensionamos
    map_img_static = None
    if map_path and os.path.exists(map_path):
        map_img_static = Image.open(map_path).convert("RGBA")
        target_w = 460 # Ancho ajustado a 540p
        w_percent = (target_w / float(map_img_static.size[0]))
        target_h = int((float(map_img_static.size[1]) * float(w_percent)))
        map_img_static = map_img_static.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # Función generadora de frames (Streaming Mode para ahorrar RAM)
    def process_frame(get_frame, t):
        bg_frame_np = get_frame(t)
        frame = Image.fromarray(bg_frame_np).convert("RGBA")
        
        # Overlay oscuro
        overlay = Image.new('RGBA', (W, H), (0, 0, 0, 110))
        frame = Image.alpha_composite(frame, overlay)
        draw = ImageDraw.Draw(frame)
        
        # Títulos
        labels = get_day_labels()
        draw.text((W//2, 90), "Lluvias en la región núcleo", font=font_title, fill="white", anchor="mm")
        draw.text((W//2, 130), labels["video_subtitle"], font=font_subtitle, fill="#dddddd", anchor="mm")
        
        # Top 5 dinámico
        y_text = 210
        for i, d in enumerate(top_5):
            if t >= (0.8 + i * 0.3):
                line = f"{i+1}. {d['localidad']}: {d['mm']} mm"
                draw.text((70, y_text), line, font=font_items, fill="white")
            y_text += 52
        
        # Mapa en t=3.0
        if t >= 3.0 and map_img_static:
            paste_x = (W - map_img_static.size[0]) // 2
            paste_y = 510
            # Sombra simple
            shadow = Image.new('RGBA', map_img_static.size, (0,0,0,120))
            frame.paste(shadow, (paste_x+5, paste_y+5), shadow)
            frame.paste(map_img_static, (paste_x, paste_y), map_img_static)
            
        draw.text((W//2, 910), "Más información en bcr.com.ar", font=font_footer, fill="#cccccc", anchor="mm")
        
        return np.array(frame.convert("RGB"))

    # Aplicamos la transformación a cada frame (sin cargar todo el video en RAM)
    final_clip = bg_clip.subclipped(0, DURATION).transform(process_frame)
    
    os.makedirs(os.path.dirname(output_mp4), exist_ok=True)
    
    # Procesamos con 1 solo hilo y sin logger para máxima estabilidad en Render
    final_clip.write_videofile(output_mp4, codec="libx264", audio=False, logger=None, threads=1)
    
    # Liberar recursos inmediatamente
    bg_clip.close()
    final_clip.close()
    
    return output_mp4

def create_animated_video_legacy(top_5, map_path, output_mp4):
    # Fallback optimizado para memoria
    W, H = 540, 960
    FPS = 8
    DURATION = 6
    bg_color = (15, 45, 80)
    font_title = ensure_font(38)
    font_items = ensure_font(32)
    
    frames = []
    for f in range(FPS * DURATION):
        t = f / FPS
        frame = Image.new('RGB', (W, H), color=bg_color)
        draw = ImageDraw.Draw(frame)
        labels = get_day_labels()
        draw.text((W//2, 100), "Lluvias en la región núcleo", font=font_title, fill="white", anchor="mm")
        draw.text((W//2, 140), labels["video_subtitle"], font=font_subtitle, fill="#dddddd", anchor="mm")
        
        y_text = 250
        for i, d in enumerate(top_5):
            if t >= (0.5+i*0.3):
                line = f"{i+1}. {d['localidad']}: {d['mm']} mm"
                draw.text((80, y_text), line, font=font_items, fill="white")
            y_text += 55
        frames.append(np.array(frame))

    clip = ImageSequenceClip(frames, fps=FPS)
    clip.write_videofile(output_mp4, codec="libx264", audio=False, logger=None, threads=1)
    clip.close()
    return output_mp4

def get_rainfall_metadata():
    url_lluvias = "https://www.bcr.com.ar/es/mercados/gea/estaciones-meteorologicas/red-de-estaciones-meteorologicas"
    r = requests.get(url_lluvias, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(r.text, 'html.parser')
    tables = soup.find_all('table')
    table = tables[1] if len(tables) > 1 else tables[0]
    data = []
    rows = table.find_all('tr')
    for row in rows[2:]:
        cols = row.find_all('td')
        if len(cols) >= 8:
            estacion = cols[0].text.strip()
            precip_str = cols[4].text.strip()
            try:
                precip_val = float(precip_str.replace(',', '.'))
                if precip_val > 0: 
                    data.append({'localidad': estacion, 'mm': precip_val})
            except ValueError:
                pass
    data.sort(key=lambda x: x['mm'], reverse=True)
    top5 = data[:5]
    labels = get_day_labels()
    texto_tweet = f"{labels['tweet_header']}\n\n"
    for d in top5:
        texto_tweet += f"- {d['localidad']}: {d['mm']} mm\n"
    texto_tweet += "\nMapas y más info en:\nhttps://www.bcr.com.ar/es/mercados/gea/clima/clima-gea/lluvias"
    url_mapa_base = "https://www.bcr.com.ar/es/mercados/gea/clima/clima-gea/lluvias"
    r_img = requests.get(url_mapa_base, headers={'User-Agent': 'Mozilla/5.0'})
    soup_img = BeautifulSoup(r_img.text, 'html.parser')
    imagen_url = None
    for img in soup_img.find_all('img'):
        src = img.get('src')
        if src and ('lluvia' in src.lower() or 'acumula' in src.lower()):
            if not src.startswith('http'):
                src = "https://www.bcr.com.ar" + src
            imagen_url = src
            break
    imagen_local_path = None
    if imagen_url:
        os.makedirs(STATIC_DIR, exist_ok=True)
        r_down = requests.get(imagen_url, headers={'User-Agent': 'Mozilla/5.0'})
        imagen_local_name = 'mapa_lluvias.jpg'
        imagen_local_path = os.path.join(STATIC_DIR, 'uploads', imagen_local_name)
        with open(imagen_local_path, 'wb') as f:
            f.write(r_down.content)
        return top5, texto_tweet, f"/static/uploads/{imagen_local_name}"
    return top5, texto_tweet, None
