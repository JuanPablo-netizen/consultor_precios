import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
import cv2
from bs4 import BeautifulSoup

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Consultor Curicó Pro",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# --- 2. FUNCIONES DE APOYO (Sonido y Auto-Enter) ---
def emitir_sonido_ok():
    # Sonido de confirmación (Beep)
    audio_url = "https://www.soundjay.com/buttons/sounds/button-37a.mp3"
    st.components.v1.html(
        f'<audio autoplay><source src="{audio_url}" type="audio/mp3"></audio>',
        height=0,
    )

def inyectar_auto_enter():
    # EL ESCÁNER RE-CENTRADO Y OPTIMIZADO
        st.components.v1.html("""
            <div id="reader" style="width:100%; border-radius:15px; overflow:hidden; background-color: #000; margin-top: -20px;"></div>
            <script src="https://unpkg.com/html5-qrcode"></script>
            <script>
                const beep = new Audio('https://www.soundjay.com/buttons/sounds/button-37a.mp3');

                function onScanSuccess(decodedText) {
                    if (!isNaN(decodedText) || decodedText.length >= 8) {
                        const input = window.parent.document.querySelector('input[placeholder="000000000"]');
                        if (input && input.value !== decodedText) {
                            beep.play().catch(e => console.log("Error sonido", e));
                            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                            nativeInputValueSetter.call(input, decodedText);
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            setTimeout(() => { input.focus(); input.blur(); }, 200);
                        }
                    }
                }

                const html5QrCode = new Html5Qrcode("reader");

                // AJUSTE DE CENTRADO DINÁMICO
                const config = { 
                    fps: 25, 
                    // Esta función fuerza a los corchetes a estar siempre en el centro matemático
                    qrbox: (viewfinderWidth, viewfinderHeight) => {
                        let width = viewfinderWidth * 0.75;
                        let height = viewfinderHeight * 0.5;
                        if (width > 300) width = 300;
                        if (height > 180) height = 180;
                        return { width: width, height: height };
                    },
                    aspectRatio: 1.333333, // Cambiamos a 4:3 que es más estable para el centrado en iOS
                    videoConstraints: {
                        facingMode: "environment",
                        width: { ideal: 1280 },
                        height: { ideal: 720 }
                    }
                };

                setTimeout(() => {
                    html5QrCode.start({ facingMode: "environment" }, config, onScanSuccess)
                    .catch(err => {
                        console.warn("Reintentando cámara...", err);
                        html5QrCode.start({ facingMode: "user" }, config, onScanSuccess);
                    });
                }, 500);
            </script>
        """, height=350) # Bajamos el height de 450 a 350 para que todo el bloque suba

# --- 3. ESTILOS CSS (Diseño Protagónico) ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    
    /* ELIMINAR EL ESPACIO MUERTO SUPERIOR POR DEFECTO DE STREAMLIT */
    .block-container {
        padding-top: 3.5rem !important; 
        padding-bottom: 1rem !important;
    }

    .sello-gestion {
        position: fixed; top: 10px; right: 10px; color: #D32F2F;
        font-size: 11px; font-weight: 800; z-index: 1000;
        text-transform: uppercase; background: rgba(255,255,255,0.8);
        padding: 4px 8px; border-radius: 5px; border: 1px solid #FEE2E2;
    }
    .product-card {
        background-color: white; padding: 25px; border-radius: 25px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.1); max-width: 450px;
        margin: 0 auto; text-align: center; border: 1px solid #F1F5F9;
    }
    .product-img { width: 260px; height: auto; max-height: 320px; object-fit: contain; border-radius: 20px; margin-bottom: 20px; }
    .product-title { font-size: 26px; font-weight: 900; color: #111; line-height: 1.1; text-transform: uppercase; }
    .product-info { font-size: 16px; color: #64748b; font-weight: 600; margin-bottom: 15px; text-transform: uppercase; }
    .price-value { font-size: 70px; font-weight: 950; color: #D32F2F; margin-bottom: 10px; letter-spacing: -2px; line-height: 1; }
    .trend-pill { display: inline-flex; align-items: center; padding: 10px 25px; border-radius: 15px; font-size: 18px; font-weight: 800; }
    .up { background-color: #FFEBEE; color: #D32F2F; }
    .down { background-color: #E8F5E9; color: #2E7D32; }
    .same { background-color: #F5F5F5; color: #616161; }
    .stTextInput > div > div > input { border-radius: 15px; text-align: center; height: 55px; font-size: 20px !important; }
    
    /* ESTILO PARA LOS BOTONES (Rojos, grandes y separados) */
    div[data-testid="stButton"] > button {
        background-color: #D32F2F !important;
        color: #FFFFFF !important;
        font-weight: 900 !important;
        font-size: 20px !important;
        height: 65px !important;
        border-radius: 15px !important;
        border: none !important;
        margin-top: 15px !important;
        margin-bottom: 15px !important;
        box-shadow: 0 8px 20px rgba(211,47,47,0.3) !important;
    }
    div[data-testid="stButton"] > button:active { background-color: #9A0007 !important; }
    </style>
""", unsafe_allow_html=True)

# --- TÍTULO PRINCIPAL SIEMPRE VISIBLE ---
st.markdown("""
    <h1 style='text-align: center; color: #D32F2F; font-size: 28px; font-weight: 900; text-transform: uppercase; margin-top: -20px; margin-bottom: 20px;'>
        Consultor de Precios Curicó 1
    </h1>
""", unsafe_allow_html=True)

# --- 4. LÓGICA DE DATOS ---
@st.cache_data(ttl=300)
def obtener_datos():
    url = 'https://drive.google.com/uc?export=download&id=1iTKUYxsQBh42zHahtDrLfvULM1o_Qsnb'
    try:
        r = requests.get(url)
        df = pd.read_excel(io.BytesIO(r.content), engine='openpyxl')
        df.columns = [str(c).strip().lower() for c in df.columns]
        mapeo = {'articulo': 'producto', 'artículo': 'producto', 'codigo': 'producto', 'descripción': 'descripcion', 'descripcion': 'descripcion'}
        df = df.rename(columns=mapeo)
        
        # --- EL TRUCO DE VELOCIDAD ---
        # Convertimos a texto y limpiamos UNA SOLA VEZ en la memoria caché
        df['producto'] = df['producto'].astype(str).str.strip()
        
        return df
    except: return None

@st.cache_data(ttl=3600)
def buscar_foto(sku):
    # Scraping rápido de foto
    url = f"https://www.tricot.cl/{sku}.html"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=2)
        soup = BeautifulSoup(r.text, 'html.parser')
        tag = soup.find("meta", property="og:image")
        if tag: return tag["content"]
    except: pass
    return f"https://www.tricot.cl/on/demandware.static/-/Sites-tricot-master/default/images/large/{sku}_1.jpg"

def decodificar_barras(foto_st):
    """
    Usa el detector nativo de OpenCV (más estable en Railway)
    """
    try:
        # Convertir imagen
        img = cv2.imdecode(np.frombuffer(foto_st.read(), np.uint8), 1)
        
        # Nuevo detector de códigos de barras de OpenCV
        detector = cv2.barcode.BarcodeDetector()
        ok, decoded_info, decoded_type, _ = detector.detectAndDecode(img)
        
        if ok and decoded_info:
            # Retornamos el primer código encontrado que no sea vacío
            return decoded_info[0]
    except Exception as e:
        print(f"Error en decodificación: {e}")
    return None

# --- 5. INTERFAZ Y FLUJO ---
if "estado" not in st.session_state:
    st.session_state.estado = "esperando"
if "modo_manual" not in st.session_state:
    st.session_state.modo_manual = False

# Pantalla de Escaneo
if st.session_state.estado == "esperando":

    if not st.session_state.modo_manual:
        st.markdown("<h3 style='text-align:center; color:#666; font-size:16px;'>APUNTE AL CÓDIGO DE BARRAS</h3>", unsafe_allow_html=True)
        
        # EL ESCÁNER (dentro del if)
        st.components.v1.html("""
            <div id="reader" style="width:100%; border-radius:15px; overflow:hidden;"></div>
            <script src="https://unpkg.com/html5-qrcode"></script>
            <script>
                const beep = new Audio('https://www.soundjay.com/buttons/sounds/button-37a.mp3');
                function onScanSuccess(decodedText) {
                    if (!isNaN(decodedText) || decodedText.length <= 13) {
                        const input = window.parent.document.querySelector('input[placeholder="000000000"]');
                        if (input && input.value !== decodedText) {
                            beep.play().catch(e => console.log("Sonido", e));
                            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                            nativeInputValueSetter.call(input, decodedText);
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            setTimeout(() => { input.focus(); input.blur(); }, 300);
                        }
                    }
                }
                const html5QrCode = new Html5Qrcode("reader");
                const config = { fps: 20, qrbox: { width: 250, height: 130 }, aspectRatio: 1.777778};
                html5QrCode.start({ facingMode: "environment" }, config, onScanSuccess);
            </script>
        """, height=380) # <- CAMBIO AQUÍ: Subimos a 320 para que no recorte la parte de abajo

        # Ocultamos la etiqueta pero dejamos el input para recibir el dato del escáner
        manual = st.text_input("DIGITE CÓDIGO", placeholder="000000000", label_visibility="collapsed")
        
        # Botón para ir al manual
        st.markdown("""
            <style>
            div[data-testid="stButton"] > button {
                background-color: #D32F2F !important;
                color: #FFFFFF !important;
                font-weight: 800 !important;
                border-radius: 15px !important;
                border: none !important;
            }
            </style>
        """, unsafe_allow_html=True)
        if st.button("✍️ CONSULTAR MANUALMENTE", use_container_width=True):
            st.session_state.modo_manual = True
            st.rerun()

    else:
        # PANTALLA MANUAL (cuando el botón se presiona)
        st.markdown("<h3 style='text-align:center; color:#666; font-size:16px;'>INGRESE EL CÓDIGO MANUALMENTE</h3>", unsafe_allow_html=True)
        
        manual = st.text_input("DIGITE CÓDIGO", placeholder="000000000")
        inyectar_auto_enter()
        
        # Botón para regresar a la cámara
        if st.button("📷 VOLVER AL ESCÁNER", use_container_width=True):
            st.session_state.modo_manual = False
            st.rerun()

    # Lógica de búsqueda ultra rápida
    if manual:
        sku_6 = str(manual).strip()[:6]
        df = obtener_datos()
        
        if df is not None:
            # Búsqueda directa sin reprocesar datos
            res = df[df['producto'].str.contains(sku_6)]
            
            if not res.empty:
                emitir_sonido_ok() # ¡BEEP!
                st.session_state.modo_manual = False # Resetea para que la próxima vez abra la cámara
                st.session_state.p = res.iloc[0]
                st.session_state.sku = sku_6
                st.session_state.estado = "resultado"
                st.rerun()
            elif len(sku_6) >= 6:
                st.error("Producto no encontrado.")

# Pantalla de Resultado Protagónico
if st.session_state.estado == "resultado":
    p, sku = st.session_state.p, st.session_state.sku
    p_act = float(p.get('precio actual', 0))
    p_nue = float(p.get('nuevo precio', 0))
    
    if p_nue > p_act: var, cls = "🔺 EL PRECIO SUBIÓ", "up"
    elif p_nue < p_act: var, cls = "🔻 EL PRECIO BAJÓ", "down"
    else: var, cls = "➖ SIN CAMBIO DE PRECIO", "same"
    
    st.markdown(f"""
        <div class="product-card">
            <img src="{buscar_foto(sku)}" class="product-img">
            <div class="product-title">{str(p.get('descripcion', 'PRODUCTO')).upper()}</div>
            <div class="product-info">{str(p.get('departamento', 'GENERAL'))} | {str(p.get('subcategoria', 'OTROS'))}</div>
            <div class="price-value">$ {p_nue:,.0f}</div>
            <div class="trend-pill {cls}">{var}</div>
            <div style="margin-top:20px; color:#999; font-size:12px; font-family:monospace;">SKU: {sku}</div>
        </div>
    """.replace(',', '.'), unsafe_allow_html=True)

    # --- ESTILO Y BOTÓN INFERIOR PARA MÓVIL ---
    st.markdown("""
        <style>
        /* Transformar el botón nativo en un botón rojo gigante, al fondo y con espacio */
        div[data-testid="stButton"] > button {
            background-color: #D32F2F !important;
            color: #FFFFFF !important;
            font-weight: 900 !important;
            font-size: 20px !important;
            height: 65px !important;
            border-radius: 15px !important;
            border: none !important;
            margin-top: 10px !important; /* El espacio que pediste */
            margin-bottom: 20px !important;
            box-shadow: 0 8px 20px rgba(211,47,47,0.3) !important;
        }
        div[data-testid="stButton"] > button:active {
            background-color: #9A0007 !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # El botón ahora aparecerá abajo de la tarjeta
    if st.button("🔄 CONSULTAR OTRO PRODUCTO", use_container_width=True):
        st.session_state.estado = "esperando"
        st.rerun()