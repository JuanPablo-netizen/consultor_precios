import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
import cv2
import base64
from bs4 import BeautifulSoup

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Consultor Curicó Pro",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- 2. FUNCIONES DE APOYO (Sonido y Auto-Enter) ---
def emitir_sonido_ok():
    audio_url = "https://www.soundjay.com/buttons/sounds/button-37a.mp3"
    st.components.v1.html(
        f'<audio autoplay><source src="{audio_url}" type="audio/mp3"></audio>',
        height=0,
    )

def inyectar_auto_enter():
    """Esta función SOLO debe contener la lógica del teclado/input"""
    st.components.v1.html("""
        <script>
        const monitor = setInterval(() => {
            const input = window.parent.document.querySelector('input[placeholder="000000000"]');
            if (input && input.value.length >= 9) {
                const e = new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true});
                input.dispatchEvent(e);
                input.blur(); // Fuerza la recarga en Streamlit
                clearInterval(monitor); // Se detiene una vez que dispara
            }
        }, 100);
        </script>
    """, height=0)

# --- 3. LÓGICA DE IMÁGENES (BYPASS UNIVERSAL) ---
@st.cache_data(ttl=3600)
def obtener_foto_bypass(sku):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    img_url = f"https://www.tricot.cl/on/demandware.static/-/Sites-tricot-master/default/images/large/{sku}_1.jpg"
    
    try:
        res = requests.get(img_url, headers=headers, timeout=3)
        
        if res.status_code != 200:
            prod_url = f"https://www.tricot.cl/{sku}.html"
            r = requests.get(prod_url, headers=headers, timeout=2)
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, 'html.parser')
            tag = soup.find("meta", property="og:image")
            if tag: 
                res = requests.get(tag["content"], headers=headers, timeout=2)

        if res.status_code == 200:
            import base64
            return f"data:image/jpeg;base64,{base64.b64encode(res.content).decode()}"
    except:
        pass
    
    return "https://via.placeholder.com/400x400.png?text=Sin+Foto+Disponible"

# --- 4. ESTILOS CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    .block-container { padding-top: 3.5rem !important; padding-bottom: 1rem !important; }
    .product-card {
        background-color: white; padding: 25px; border-radius: 25px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.1); max-width: 450px;
        margin: 0 auto; text-align: center; border: 1px solid #F1F5F9;
    }
    .product-img { width: 100%; max-width: 280px; height: auto; border-radius: 20px; margin-bottom: 20px; }
    .product-title { font-size: 26px; font-weight: 900; color: #111; text-transform: uppercase; }
    .price-value { font-size: 70px; font-weight: 950; color: #D32F2F; margin-bottom: 10px; line-height: 1; }
    .trend-pill { display: inline-flex; align-items: center; padding: 10px 25px; border-radius: 15px; font-size: 18px; font-weight: 800; }
    .up { background-color: #FFEBEE; color: #D32F2F; }
    .down { background-color: #E8F5E9; color: #2E7D32; }
    .same { background-color: #F5F5F5; color: #616161; }
    
    div[data-testid="stButton"] > button {
        background-color: #D32F2F !important;
        color: #FFFFFF !important;
        font-weight: 900 !important;
        font-size: 20px !important;
        height: 65px !important;
        border-radius: 15px !important;
        box-shadow: 0 8px 20px rgba(211,47,47,0.3) !important;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align: center; color: #D32F2F; font-size: 28px; font-weight: 900; text-transform: uppercase; margin-top: -20px; margin-bottom: 20px;'>Consultor de Precios Curicó 1</h1>", unsafe_allow_html=True)

# --- 5. LÓGICA DE DATOS ---
@st.cache_data(ttl=300)
def obtener_datos():
    url = 'https://drive.google.com/uc?export=download&id=1iTKUYxsQBh42zHahtDrLfvULM1o_Qsnb'
    try:
        r = requests.get(url)
        df = pd.read_excel(io.BytesIO(r.content), engine='openpyxl')
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.rename(columns={'articulo': 'producto', 'artículo': 'producto', 'codigo': 'producto', 'descripción': 'descripcion'})
        df['producto'] = df['producto'].astype(str).str.strip()
        return df
    except: return None

# --- 6. INTERFAZ Y FLUJO ---
if "estado" not in st.session_state: st.session_state.estado = "esperando"
if "modo_manual" not in st.session_state: st.session_state.modo_manual = False

if st.session_state.estado == "esperando":
    if not st.session_state.modo_manual:
        st.markdown("<h3 style='text-align:center; color:#666; font-size:16px;'>APUNTE AL CÓDIGO DE BARRAS</h3>", unsafe_allow_html=True)
        
        # ESCÁNER FULL-FRAME (SIN CORCHETES / BLOQUEO QR / AUTO-ENTER / IPHONE FIX)
        st.components.v1.html("""
            <style>
                #reader-container { position: relative; width: 100%; height: 260px; border-radius: 20px; overflow: hidden; background: #000; border: 3px solid #D32F2F; margin-top: -10px; }
                #reader__scan_region, #reader canvas, .html5-qrcode-element, #reader__status_span { display: none !important; }
                #reader video { object-fit: cover !important; height: 260px !important; width: 100% !important; transform: scaleX(1) !important; }
                .laser { position: absolute; top: 50%; left: 10%; width: 80%; height: 2px; background: #D32F2F; box-shadow: 0 0 10px #F00; z-index: 100; animation: scan 1.5s infinite; }
                @keyframes scan { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
            </style>
            
            <div id="reader-container"><div class="laser"></div><div id="reader"></div></div>
            
            <script src="https://unpkg.com/html5-qrcode"></script>
            <script>
                // Formatos 1D (Bloquea QR) y activa motor nativo de iPhone
                const scanner = new Html5Qrcode("reader", { 
                    formatsToSupport: [Html5QrcodeSupportedFormats.EAN_13, Html5QrcodeSupportedFormats.EAN_8, Html5QrcodeSupportedFormats.CODE_128],
                    experimentalFeatures: { useBarCodeDetectorIfSupported: true } 
                });
                
                // Resolución forzada y CÁMARA TRASERA ASEGURADA
                const config = { 
                    fps: 30, 
                    aspectRatio: 1.0, 
                    videoConstraints: { 
                        facingMode: "environment", // Fuerza cámara principal (trasera)
                        width: { ideal: 1280 }, 
                        height: { ideal: 720 } 
                    } 
                };
                
                scanner.start({ facingMode: "environment" }, config, (txt) => {
                    const input = window.parent.document.querySelector('input[placeholder="000000000"]');
                    if (input && input.value !== txt) {
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                        setter.call(input, txt);
                        
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        
                        const e = new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true});
                        input.dispatchEvent(e);
                        input.blur(); // El gatillo definitivo
                    }
                });
            </script>
        """, height=280)

        manual = st.text_input("DIGITE CÓDIGO", placeholder="000000000", label_visibility="collapsed")
        inyectar_auto_enter()
        
        if st.button("✍️ CONSULTAR MANUALMENTE", use_container_width=True):
            st.session_state.modo_manual = True
            st.rerun()
    else:
        st.markdown("<h3 style='text-align:center; color:#666; font-size:16px;'>INGRESE EL CÓDIGO MANUALMENTE</h3>", unsafe_allow_html=True)
        manual = st.text_input("DIGITE CÓDIGO", placeholder="000000000")
        inyectar_auto_enter()
        
        if st.button("📷 VOLVER AL ESCÁNER", use_container_width=True):
            st.session_state.modo_manual = False
            st.rerun()

    if manual:
        sku_6 = str(manual).strip()[:6]
        df = obtener_datos()
        if df is not None:
            res = df[df['producto'].str.contains(sku_6)]
            if not res.empty:
                emitir_sonido_ok()
                st.session_state.modo_manual = False
                st.session_state.p = res.iloc[0]
                st.session_state.sku = sku_6
                st.session_state.estado = "resultado"
                st.rerun()

# --- PANTALLA DE RESULTADO ---
if st.session_state.estado == "resultado":
    p, sku = st.session_state.p, st.session_state.sku
    img_b64 = obtener_foto_bypass(sku)
    
    p_act, p_nue = float(p.get('precio actual', 0)), float(p.get('nuevo precio', 0))
    var, cls = ("🔻 EL PRECIO BAJÓ", "down") if p_nue < p_act else ("🔺 EL PRECIO SUBIÓ", "up") if p_nue > p_act else ("➖ SIN CAMBIO", "same")
    
    st.markdown(f"""
        <div class="product-card">
            <img src="{img_b64}" class="product-img">
            <div class="product-title">{str(p.get('descripcion', 'PRODUCTO')).upper()}</div>
            <div class="price-value">$ {p_nue:,.0f}</div>
            <div class="trend-pill {cls}">{var}</div>
            <div style="margin-top:20px; color:#999; font-size:12px;">SKU: {sku}</div>
        </div>
    """.replace(',', '.'), unsafe_allow_html=True)

    if st.button("🔄 CONSULTAR OTRO PRODUCTO", use_container_width=True):
        st.session_state.estado = "esperando"
        st.rerun()