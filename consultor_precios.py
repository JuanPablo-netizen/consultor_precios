import streamlit as st
import pandas as pd
import requests
import io
import re
import fitz
import unicodedata
import plotly.express as px
from fpdf import FPDF
from datetime import datetime
import concurrent.futures


def normalizar_texto_pdf(texto):
    """
    Normaliza el texto a NFC (forma precompuesta) para evitar que
    fpdf2 falle con FPDFUnicodeEncodingException cuando el texto
    viene en NFD (por ejemplo, nombres de carpetas/archivos de Drive
    creados desde macOS, donde "ó" se guarda como "o" + acento suelto).
    """
    if texto is None:
        return texto
    return unicodedata.normalize('NFC', str(texto))

# Diccionario inteligente: unifica plurales (S opcional), abreviaturas y sinónimos.
# Lo usa clasificar_tipo_producto_inteligente() para normalizar la descripción
# antes de agrupar por Tipo de Producto.
SINONIMOS_Y_ABREVIATURAS = {
    # --- Plurales y Variantes Frecuentes ---
    r'\bSRAS?\b': 'SENORA',
    r'\bSENORAS?\b': 'SENORA',
    r'\bSEÑORAS?\b': 'SENORA',
    r'\bENCAJES?\b': 'ENCAJE',
    r'\bMANGAS?\b': 'MANGA',
    r'\bALGODONES?\b': 'ALGODON',
    r'\bESTAMPADAS?\b': 'ESTAMPADO',
    r'\bESTAMPADOS\b': 'ESTAMPADO',
    r'\bCOLORES?\b': 'COLOR',

    # --- Abreviaturas Comunes ---
    r'\bC/R\b': 'CUELLO REDONDO',
    r'\bC/V\b': 'CUELLO V',
    r'\bC/ALTO\b': 'CUELLO ALTO',
    r'\bM/L\b': 'MANGA LARGA',
    r'\bM/C\b': 'MANGA CORTA',
    r'\bS/M\b': 'SIN MANGA',
    r'\bPTL\b': 'PANTALON',
    r'\bPOL\b': 'POLERA',
    r'\bZAP\b': 'ZAPATO',
    r'\bINF\b': 'INFANTIL',
}

def categorias_representativas(df, columna_categoria, columna_stock='stock', umbral=0.60, max_categorias=9):
    """
    Devuelve la lista de categorías (de mayor a menor stock) necesarias para
    concentrar 'umbral' % del stock total de df, con max_categorias como
    tope. Misma lógica de corte que usa crear_donut() para decidir qué
    porciones mostrar, pero expuesta aparte para poder filtrar otros
    gráficos (ej. Stock por Rango de Precio) por ese mismo subconjunto.
    """
    agrupado = df.groupby(columna_categoria)[columna_stock].sum().sort_values(ascending=False)
    total = agrupado.sum()
    if total <= 0:
        return []
    acumulado = agrupado.cumsum() / total
    n_incluir = int((acumulado < umbral).sum()) + 1
    n_incluir = max(1, min(n_incluir, max_categorias, len(agrupado)))
    return agrupado.index[:n_incluir].tolist()

def clasificar_tipo_producto_inteligente(df, columna_desc='descripcion', columna_stock='stock', max_palabras=4):
    """
    Agrupa productos para el gráfico "Stock por Tipo de Producto" buscando
    coincidencias directamente en la columna DESCRIPCIÓN, en vez de un
    diccionario fijo de patrones (el antiguo FAMILIAS_PRODUCTO, ya
    eliminado), que resultaba demasiado genérico (ej. todo lo que dijera
    "BLUSA" caía en una sola categoría, perdiendo el detalle real de la
    descripción).

    Para cada producto se prueba primero con sus primeras 4 palabras
    (máxima especificidad, ej. "POLERA RIB CON BOTON"); si esa combinación
    exacta es demasiado poco representativa (aparece en muy poco stock),
    se retrocede a 3, luego 2, luego 1 palabra, hasta encontrar el nivel
    en el que ese grupo sí concentra una porción relevante del stock total.
    Así descripciones únicas o poco frecuentes se consolidan bajo un
    término más general en vez de quedar como porciones microscópicas.
    """
    df = df.copy()
    total_stock = pd.to_numeric(df[columna_stock], errors='coerce').fillna(0).sum()
    # Un grupo se considera representativo si concentra al menos 0.5% del
    # stock total; por debajo de eso, se prueba con una combinación más
    # genérica (menos palabras).
    min_stock_grupo = total_stock * 0.005

    def normalizar(desc):
        texto = str(desc).strip().upper()
        if not texto or texto == "NAN":
            return ""
        for patron, reemplazo in SINONIMOS_Y_ABREVIATURAS.items():
            texto = re.sub(patron, reemplazo, texto)
        return texto

    palabras_por_fila = df[columna_desc].apply(normalizar).apply(lambda t: t.split() if t else [])

    # Para cada largo de N palabras (4 -> 1), se calcula cuánto stock
    # concentra cada combinación de "primeras N palabras" en toda la base.
    stock_por_prefijo = {}
    for n in range(max_palabras, 0, -1):
        prefijos_n = palabras_por_fila.apply(lambda p: " ".join(p[:n]) if len(p) >= n else None)
        stock_por_prefijo[n] = df.groupby(prefijos_n)[columna_stock].sum()

    def elegir_grupo(palabras):
        if not palabras:
            return "SIN DESCRIPCIÓN"
        for n in range(max_palabras, 0, -1):
            if len(palabras) >= n:
                prefijo = " ".join(palabras[:n])
                if stock_por_prefijo[n].get(prefijo, 0) >= min_stock_grupo:
                    return prefijo
        # Si ni con 1 palabra se alcanza el mínimo (caso raro), se usa
        # igual para no perder el dato.
        return palabras[0]

    df['patron_detectado'] = palabras_por_fila.apply(elegir_grupo)
    return df

# --- 0. CONEXIÓN A GOOGLE DRIVE (carpetas públicas, sin cuenta de servicio) ---
# Requisitos:
#  1) En Google Cloud Console: habilita "Google Drive API" y crea una API Key
#     (Credenciales > Crear credenciales > Clave de API). Restríngela a "Drive API".
#  2) Las carpetas PDF / CATALOGOS / INSTRUCTIVOS (y todo su contenido) deben estar
#     compartidas como "Cualquiera con el enlace: Lector", igual que tu archivo de precios.
#  3) Reemplaza los 3 valores de abajo con tus datos reales.

DRIVE_API_KEY = "AIzaSyAy8ii9mbAfcgM5DJgDHNEQ42hAQYH4UGQ"

# ID de la carpeta "CATALOGOS" (se obtiene abriendo la carpeta en Drive y copiando
# el código que aparece al final de la URL: drive.google.com/drive/folders/AQUI_VA_EL_ID)
ID_CARPETA_CATALOGOS = "136DkzTJ0YUgPWWQz8W9EKhz08qNKd0pP"

# ID de la carpeta "INSTRUCTIVOS"
ID_CARPETA_INSTRUCTIVOS = "1rUSPtruuUT3j00r-nauGq0XGNMim786z"


@st.cache_data(ttl=3600, show_spinner=False)
def listar_contenido_drive(folder_id):
    """
    Lista subcarpetas y archivos PDF dentro de una carpeta pública de Drive,
    usando solo la API Key (sin login ni cuenta de servicio).
    Devuelve (carpetas, archivos), cada uno como lista de dicts {id, name}.
    """
    url = "https://www.googleapis.com/drive/v3/files"
    params = {
        "q": f"'{folder_id}' in parents and trashed = false",
        "fields": "files(id, name, mimeType)",
        "orderBy": "folder,name",
        "pageSize": 200,
        "key": DRIVE_API_KEY,
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    items = r.json().get("files", [])
    carpetas = [i for i in items if i["mimeType"] == "application/vnd.google-apps.folder"]
    archivos = [i for i in items if i["mimeType"] == "application/pdf"]
    return carpetas, archivos


def descargar_pdf_drive(file_id):
    """Descarga los bytes de un PDF público de Drive (mismo patrón de URL que ya usas)."""
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content


@st.cache_data(ttl=3600, show_spinner=False)
def listar_pdfs_recursivo(folder_id, ruta=""):
    """
    Recorre recursivamente una carpeta de Drive (y todas sus subcarpetas)
    y devuelve la lista completa de PDFs encontrados, cada uno con la ruta
    de subcarpetas en la que está ubicado (para mostrarla como referencia).
    Las subcarpetas se consultan en paralelo para acelerar la primera carga.
    """
    carpetas, archivos = listar_contenido_drive(folder_id)
    resultado = [{"id": a["id"], "name": a["name"], "ruta": ruta} for a in archivos]

    if carpetas:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futuros = {
                executor.submit(
                    listar_pdfs_recursivo,
                    c["id"],
                    f"{ruta} / {c['name']}" if ruta else c["name"]
                ): c
                for c in carpetas
            }
            for futuro in concurrent.futures.as_completed(futuros):
                resultado.extend(futuro.result())

    return resultado


# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Consultor Curicó Pro",
    layout="wide",
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
    st.components.v1.html("""
        <script>
        const monitor = setInterval(() => {
            const input = window.parent.document.querySelector('input[placeholder="000000000"]');
            if (input && input.value.length >= 9) {
                clearInterval(monitor);
                if (navigator.vibrate) {
                    navigator.vibrate(200);
                }
                input.focus(); 
                setTimeout(() => { 
                    input.blur(); 
                }, 50);
            }
        }, 100);
        </script>
    """, height=0)

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
    .stTextInput input {
        text-align: center !important;
        font-size: 28px !important;
        font-weight: 900 !important;
        letter-spacing: 3px !important;
        color: #D32F2F !important;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("<h1 style='text-align: center; color: #D32F2F; font-size: 28px; font-weight: 900; text-transform: uppercase; margin-top: -20px; margin-bottom: 20px;'>Consultor de Precios Curicó 1</h1>", unsafe_allow_html=True)

# --- 5. LÓGICA DE DATOS ---
@st.cache_data(ttl=43200)
def obtener_datos():
    url = 'https://drive.google.com/uc?export=download&id=1iTKUYxsQBh42zHahtDrLfvULM1o_Qsnb'
    try:
        r = requests.get(url)
        df = pd.read_excel(io.BytesIO(r.content), engine='calamine')
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.rename(columns={'articulo': 'producto', 'artículo': 'producto', 'codigo': 'producto', 'descripción': 'descripcion'})
        df['producto'] = pd.to_numeric(df['producto'], errors='coerce')
        df = df.dropna(subset=['producto'])
        df['producto'] = df['producto'].astype('int64').astype(str).str.strip()
        return df
    except Exception as e:
        st.error(f"⚠️ Error técnico detallado: {e}")
        return None

@st.cache_data(ttl=3600)
def cargar_base_precios():
    url = 'https://drive.google.com/uc?export=download&id=1iTKUYxsQBh42zHahtDrLfvULM1o_Qsnb'
    response = requests.get(url)
    return pd.read_excel(io.BytesIO(response.content))

def combinar_pdfs(lista_pdfs_bytes):
    """Combina varios PDFs (uno por hoja) en un solo archivo PDF final."""
    combinado = fitz.open()
    for pdf_bytes in lista_pdfs_bytes:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc_temp:
            combinado.insert_pdf(doc_temp)
    data = combinado.tobytes()
    combinado.close()
    return data


def generar_pdf_simple(image_bytes, titulo):
    titulo = normalizar_texto_pdf(titulo)

    # Detectar la orientación real de la imagen (hoja sin códigos/tabla)
    # para no forzar siempre horizontal.
    try:
        pix_tmp = fitz.Pixmap(image_bytes)
        img_w, img_h = pix_tmp.width, pix_tmp.height
    except Exception:
        img_w, img_h = 1, 1  # fallback neutro, no debería pasar

    orientacion = 'P' if img_h > img_w else 'L'

    pdf = FPDF(orientation=orientacion, unit='mm', format='Letter')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, titulo, ln=True, align='C')
    pdf.ln(5)

    # Escalar la imagen para que quepa completa y centrada,
    # respetando su proporción original, sea vertical u horizontal.
    margen = 10
    y_img = 25
    max_w = pdf.w - 2 * margen
    max_h = pdf.h - y_img - margen

    escala = min(max_w / img_w, max_h / img_h)
    w_final = img_w * escala
    h_final = img_h * escala
    x_final = (pdf.w - w_final) / 2

    pdf.image(io.BytesIO(image_bytes), x=x_final, y=y_img, w=w_final, h=h_final, type='PNG')
    return bytes(pdf.output(dest='S'))

def generar_pdf_completo(image_bytes, df, titulo, advertencias=""):
    titulo = normalizar_texto_pdf(titulo)
    pdf = FPDF(orientation='L', unit='mm', format='Letter')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, titulo, ln=True, align='C')
    pdf.ln(5)
    pdf.image(io.BytesIO(image_bytes), x=10, y=25, w=120, type='PNG')
    pdf.set_xy(135, 25)
    pdf.set_font("Arial", 'B', 7)
    headers = ["Subcategoria", "Código", "Descripción", "Precio Hoy", "Stock", "Vta Un."]
    col_widths = [35, 15, 45, 20, 12, 12]
    pdf.set_fill_color(80, 80, 80)
    pdf.set_text_color(255, 255, 255)
    for j, col in enumerate(headers):
        pdf.cell(col_widths[j], 8, col, border=1, align='C', fill=True)
    pdf.ln()
    
    # Bucle de datos modificado para aplicar solo negrita si la venta es 0 Y tiene stock
    for _, row in df.iterrows():
        pdf.set_x(135)
        
        try:
            if float(row['VENTA MES']) == 0 and float(row['STOCK']) > 0:
                pdf.set_font("Arial", 'B', 7) # Solo negrita
            else:
                pdf.set_font("Arial", '', 7)
        except:
            pdf.set_font("Arial", '', 7)
            
        pdf.set_text_color(0, 0, 0)
        usar_relleno = False
            
        for j, val in enumerate(row):
            pdf.cell(col_widths[j], 8, str(val), border=1, align='C', fill=usar_relleno)
        pdf.ln()
        
    if advertencias:
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 8)
        pdf.set_text_color(255, 0, 0)
        pdf.set_x(135)
        pdf.multi_cell(149, 6, advertencias, border=0)
        pdf.set_text_color(0, 0, 0)
    return bytes(pdf.output(dest='S'))

def generar_pdf(df, depto, subcat, filtro_venta):
    # Definición exacta para las 9 columnas en milímetros (Suma total: 260 mm)
    # [PRODUCTO, DESCRIPCIÓN, MARCA, TEMPORADA, STOCK, PRECIO, U.VENDIDAS, OBSERVACIONES, STOCK EN SALA]
    col_widths = [18, 65, 25, 25, 15, 22, 20, 45, 25] 
    
    anchos_reales = col_widths[:len(df.columns)]  
    total_width = sum(anchos_reales)              
    x_start = (279.4 - total_width) / 2  # Centrado perfecto basado en el total real (Márgenes de ~9.7 mm)

    class PDFReport(FPDF):
        def header(self):
            # Encabezado y Títulos
            self.set_y(10)
            self.set_font("Arial", 'B', 14)
            self.set_text_color(211, 47, 47)
            self.cell(0, 10, "REPORTE DE STOCK", ln=True, align='C')
            
            self.set_font("Arial", 'B', 10)
            self.set_text_color(80, 80, 80)
            subtitulo = f"Depto: {depto} | Subcategoria: {subcat} | Tipo: {filtro_venta}"
            self.cell(0, 8, subtitulo, ln=True, align='C')
            self.ln(5)
            
            # Configuración de Encabezados de Tabla
            self.set_font("Arial", 'B', 7)
            self.set_fill_color(211, 47, 47)
            self.set_text_color(255, 255, 255)
            
            self.set_x(x_start)
            for i, header in enumerate(df.columns):
                w = col_widths[i] if i < len(col_widths) else 25
                self.cell(w, 8, str(header), border=1, align='C', fill=True)
            self.ln()

    pdf = PDFReport(orientation='L', unit='mm', format='Letter')
    pdf.add_page()
    
    # Filas de Datos
    pdf.set_font("Arial", '', 7)
    pdf.set_text_color(0, 0, 0)
    for _, row in df.iterrows():
        pdf.set_x(x_start)
        for i, val in enumerate(row):
            w = col_widths[i] if i < len(col_widths) else 25
            texto = str(val)[:50] if i == 1 else str(val) # Trunca la descripción si es muy larga
            pdf.cell(w, 8, texto, border=1, align='C')
        pdf.ln()
        
    return bytes(pdf.output(dest='S'))

# --- 5.5 BOTÓN DE SINCRONIZACIÓN MANUAL ---
with st.sidebar:
    st.markdown("### ⚙️ Administración")
    st.info("Usa este botón para descargar inmediatamente los precios más recientes desde Drive.")
    if st.button("🔄 Sincronizar Base de Precios", use_container_width=True):
        st.cache_data.clear()
        st.success("✅ Memoria borrada. Cargando nuevos datos...")
        import time
        time.sleep(1)
        st.rerun()

    st.markdown("---")
    st.markdown("### 📋 Consultas Masivas")
    if st.button("📦 Ver Listado de Stock", use_container_width=True):
        st.session_state.vista_actual = "listado"
        st.rerun()
    if st.button("📊 Análisis de Stock", use_container_width=True):
        st.session_state.vista_actual = "grafico"
        st.rerun()

    st.markdown("---")
    st.markdown("### ⏰ Archivos PDF")
    if st.button("⚙️ Revisa Catálogos e Instructivos", use_container_width=True):
        st.session_state.vista_actual = "instructivos"
        st.rerun()

# --- 6. INTERFAZ Y FLUJO ---
if "estado" not in st.session_state: st.session_state.estado = "esperando"
if "modo_manual" not in st.session_state: st.session_state.modo_manual = False
if "vista_actual" not in st.session_state: st.session_state.vista_actual = "escaner"

# =======================================================
# --- VISTA 1: LISTADO DE STOCK ---
# =======================================================
if st.session_state.vista_actual == "listado":
    st.markdown("<h3 style='text-align: center; color: #D32F2F; font-weight: 900;'>📦 BÚSQUEDA DE STOCK</h3>", unsafe_allow_html=True)
    
    df_raw = obtener_datos()
    
    if df_raw is not None:
        df = df_raw.copy()
        
        hoy = datetime.now()
        col_venta_mes = f"ventas {hoy.strftime('%m')}"

        cols_texto = ['linea', 'departamento', 'subcategoria', 'temporada', 'marca']
        for c in cols_texto:
            df[c] = df[c].astype(str).str.strip().str.upper().replace(['NAN', 'NONE', 'N/A', ''], 'SIN DATO')

        f1_c1, f1_col2, f1_col3, f1_col4 = st.columns(4)
        with f1_c1:
            lista_lineas = sorted([str(x) for x in df['linea'].unique() if str(x) != "SIN DATO"])
            f_linea = st.selectbox("Línea", ["Todas"] + lista_lineas)
        with f1_col2:
            df_l = df if f_linea == "Todas" else df[df['linea'] == f_linea]
            lista_deptos = sorted([str(x) for x in df_l['departamento'].unique() if str(x) != "SIN DATO"])
            f_depto = st.selectbox("Departamento", ["Todos"] + lista_deptos)
        with f1_col3:
            df_d = df_l if f_depto == "Todos" else df_l[df_l['departamento'] == f_depto]
            lista_subs = sorted([str(x) for x in df_d['subcategoria'].unique() if str(x) != "SIN DATO"])
            f_sub = st.selectbox("Subcategoría", ["Todas"] + lista_subs)
        with f1_col4:
            df_s = df_d if f_sub == "Todas" else df_d[df_d['subcategoria'] == f_sub]
            lista_marcas = sorted([str(x) for x in df_s['marca'].unique() if str(x) != "SIN DATO"])
            f_marca = st.selectbox("Marca", ["Todas"] + lista_marcas)

        f2_c1, f2_c2, f2_c3, f2_c4 = st.columns(4)
        with f2_c1:
            lista_temp = sorted([str(x) for x in df_s['temporada'].unique() if str(x) != "SIN DATO"])
            f_temp = st.selectbox("Temporada", ["Todas"] + lista_temp)
        with f2_c2:
            f_venta_cero = st.selectbox("Filtrar Venta 0", ["Ambos", "Solo Venta 0", "Solo con Venta"])
        with f2_c3:
            lista_precios = sorted([float(x) for x in df_s['nuevo precio'].unique() if pd.to_numeric(x, errors='coerce') > 0])
            f_precio = st.selectbox("Precio", ["Todos"] + lista_precios, format_func=lambda x: f"${int(x):,}".replace(",", ".") if x != "Todos" else x)
        with f2_c4:
            # Lista los valores reales que existen en la columna 'observaciones'
            # (pueden ser texto o números como "0", "100", etc.), en vez de
            # solo un sí/no genérico.
            obs_validas = df_s['observaciones'].dropna().astype(str).str.strip()
            obs_validas = obs_validas[
                (obs_validas != '') &
                (obs_validas.str.upper() != 'SIN DATO') &
                (obs_validas.str.lower() != 'nan')
            ]
            lista_obs = sorted(obs_validas.unique().tolist())
            opciones_obs = ["Todas", "Solo sin Observaciones"] + lista_obs
            f_obs = st.selectbox("Observaciones", opciones_obs)

        col_c1, = st.columns(1)
        with col_c1:
            f_pareto = st.checkbox("80% del Stock")

        f_buscar = st.text_input("🔎 Busqueda Específica", placeholder="Ej: Vest, Denim, etc.")

        df_mostrar = df_s.copy()
        if f_temp != "Todas": df_mostrar = df_mostrar[df_mostrar['temporada'] == f_temp]
        if f_marca != "Todas": df_mostrar = df_mostrar[df_mostrar['marca'] == f_marca]
        if f_precio != "Todos": df_mostrar = df_mostrar[df_mostrar['nuevo precio'] == f_precio]
        if f_buscar.strip():
            df_mostrar = df_mostrar[
                df_mostrar['descripcion'].astype(str).str.upper().str.contains(f_buscar.strip().upper(), na=False)
            ]
        
        if f_venta_cero == "Solo Venta 0":
            df_mostrar = df_mostrar[df_mostrar[col_venta_mes] == 0]
        elif f_venta_cero == "Solo con Venta":
            df_mostrar = df_mostrar[df_mostrar[col_venta_mes] > 0]
        
        if f_obs == "Solo sin Observaciones":
            df_mostrar = df_mostrar[
                (df_mostrar['observaciones'].isna()) |
                (df_mostrar['observaciones'].astype(str).str.upper() == 'SIN DATO') |
                (df_mostrar['observaciones'].astype(str).str.lower() == 'nan') |
                (df_mostrar['observaciones'].astype(str).str.strip() == '')
            ]
        elif f_obs != "Todas":
            df_mostrar = df_mostrar[df_mostrar['observaciones'].astype(str).str.strip() == f_obs]
        
        if f_pareto:
            df_mostrar = df_mostrar.sort_values(by='stock', ascending=False)
            total_st = df_mostrar['stock'].sum()
            if total_st > 0:
                df_mostrar['cum_stock'] = df_mostrar['stock'].cumsum()
                df_mostrar = df_mostrar[df_mostrar['cum_stock'] <= (0.8 * total_st)]
                df_mostrar = df_mostrar.drop(columns=['cum_stock'])

        total_skus = len(df_mostrar)
        if total_skus > 0:
            skus_con_venta = len(df_mostrar[df_mostrar[col_venta_mes] > 0])
            skus_venta_0 = len(df_mostrar[(df_mostrar[col_venta_mes] == 0) & (df_mostrar['stock'] > 0)])
            skus_sin_stock = len(df_mostrar[df_mostrar['stock'] <= 0])
            
            pct_v0 = (skus_venta_0 / total_skus) * 100
            pct_con_v = (skus_con_venta / total_skus) * 100
            pct_sin_stock = (skus_sin_stock / total_skus) * 100
            
            mensaje_metricas = (
                f"🔍 {skus_venta_0:,} SKU venta 0 ({pct_v0:.1f}%) | "
                f"{skus_con_venta:,} SKU con venta ({pct_con_v:.1f}%) | "
                f"{skus_sin_stock:,} SKU stock ≤ 0 ({pct_sin_stock:.1f}%) - Mes en Curso"
            ).replace(',', '.')

            if pct_v0 > 40:
                st.error(mensaje_metricas)
            else:
                st.success(mensaje_metricas)

            # --- MODIFICADO: Se añade 'observaciones' al final del mapa ---
            mapa_columnas = {
                'producto': 'PRODUCTO', 'descripcion': 'DESCRIPCIÓN', 'marca': 'MARCA',
                'temporada': 'TEMPORADA', 'stock': 'STOCK', 'nuevo precio': 'PRECIO',
                col_venta_mes: 'U. VENDIDAS', 'observaciones': 'OBSERVACIONES'
            }
            df_vista = df_mostrar[[c for c in mapa_columnas.keys() if c in df_mostrar.columns]].rename(columns=mapa_columnas)
            df_vista['PRECIO'] = pd.to_numeric(df_vista['PRECIO'], errors='coerce').fillna(0)
            df_vista['STOCK'] = pd.to_numeric(df_vista['STOCK'], errors='coerce').fillna(0).astype(int)
            df_vista['U. VENDIDAS'] = pd.to_numeric(df_vista['U. VENDIDAS'], errors='coerce').fillna(0).astype(int)
            
            # --- NUEVO: Limpieza de la columna OBSERVACIONES para evitar textos 'nan' ---
            if 'OBSERVACIONES' in df_vista.columns:
                df_vista['OBSERVACIONES'] = df_vista['OBSERVACIONES'].fillna('').astype(str).replace(['nan', 'NAN', 'None', 'SIN DATO'], '')
                
            # --- MODIFICADO: Ordenamiento condicional según el filtro seleccionado ---
            if f_obs != "Todas":
                df_vista = df_vista.sort_values(by='OBSERVACIONES', ascending=True).reset_index(drop=True)
            else:
                df_vista = df_vista.sort_values(by='STOCK', ascending=False).reset_index(drop=True)

            def efecto_cebra(row):
                return ['background-color: #F8FAFC' if row.name % 2 == 0 else 'background-color: #FFFFFF' for _ in row]

            st.dataframe(
                df_vista.style
                .format({'PRECIO': lambda x: f"${int(x):,}".replace(",", ".") if x > 0 else "", 'STOCK': "{:d}", 'U. VENDIDAS': "{:d}"})
                .apply(efecto_cebra, axis=1)
                .bar(subset=['STOCK'], color='#FEE2E2', align='left', vmin=0),
                use_container_width=True, hide_index=True
            )

            t_stock = int(df_vista['STOCK'].sum())
            col_t1, col_t2 = st.columns([2, 1])
            with col_t1:
                st.markdown(f"""
                    <div style='background-color:#FEE2E2;padding:10px;border-radius:10px;text-align:center;border:2px solid #D32F2F;margin-bottom:10px;'>
                        <span style='color:#D32F2F;font-weight:900;font-size:18px;'>TOTAL STOCK FILTRADO: {t_stock:,}</span>
                    </div>
                """.replace(',', '.'), unsafe_allow_html=True)
            with col_t2:
                # --- MODIFICADO: Formateo de precio chileno y asignación para exportación ---
                df_pdf = df_vista.copy()
                df_pdf['PRECIO'] = df_pdf['PRECIO'].apply(lambda x: f"${int(x):,}".replace(",", ".") if x > 0 else "$0")
                df_pdf['STOCK EN SALA'] = ""
                
                pdf_bytes = generar_pdf(df_pdf, f_depto, f_sub, f_venta_cero)
                st.download_button(
                    label="📥 Descargar PDF",
                    data=pdf_bytes,
                    file_name=f"Stock_Curico_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        else:
            st.warning("⚠️ No se encontraron productos.")

        if st.button("VOLVER AL CONSULTOR DE PRECIOS", use_container_width=True):
            st.session_state.vista_actual = "escaner"
            st.rerun()
    else:
        st.error("No se pudo cargar la base de datos.")

# =======================================================
# --- VISTA 1.5: GRÁFICO DE STOCK (TORTAS MODERNAS) ---
# =======================================================
elif st.session_state.vista_actual == "grafico":
    st.markdown("<h3 style='text-align: center; color: #D32F2F; font-weight: 900;'>📊 ANÁLISIS DE STOCK</h3>", unsafe_allow_html=True)

    df_raw = obtener_datos()

    if df_raw is not None:
        df = df_raw.copy()

        hoy = datetime.now()
        col_venta_mes = f"ventas {hoy.strftime('%m')}"

        cols_texto = ['linea', 'departamento', 'subcategoria', 'temporada', 'marca']
        for c in cols_texto:
            df[c] = df[c].astype(str).str.strip().str.upper().replace(['NAN', 'NONE', 'N/A', ''], 'SIN DATO')

        # --- Filtros: Línea, Departamento, Subcategoría y Temporada (en cascada) ---
        g_c1, g_c2, g_c3, g_c4 = st.columns(4)
        with g_c1:
            lista_lineas = sorted([str(x) for x in df['linea'].unique() if str(x) != "SIN DATO"])
            g_linea = st.selectbox("Línea", ["Todas"] + lista_lineas, key="g_linea")
        with g_c2:
            df_l = df if g_linea == "Todas" else df[df['linea'] == g_linea]
            lista_deptos = sorted([str(x) for x in df_l['departamento'].unique() if str(x) != "SIN DATO"])
            g_depto = st.selectbox("Departamento", ["Todos"] + lista_deptos, key="g_depto")
        with g_c3:
            df_d = df_l if g_depto == "Todos" else df_l[df_l['departamento'] == g_depto]
            lista_subcats = sorted([str(x) for x in df_d['subcategoria'].unique() if str(x) != "SIN DATO"])
            g_subcat = st.selectbox("Subcategoría", ["Todas"] + lista_subcats, key="g_subcat")
        with g_c4:
            df_sc = df_d if g_subcat == "Todas" else df_d[df_d['subcategoria'] == g_subcat]
            lista_temporadas = sorted([str(x) for x in df_sc['temporada'].unique() if str(x) != "SIN DATO"])
            g_temp = st.selectbox("Temporada", ["Todas"] + lista_temporadas, key="g_temp")

        df_g = df_sc if g_temp == "Todas" else df_sc[df_sc['temporada'] == g_temp]
        df_g = df_g.copy()
        df_g['stock'] = pd.to_numeric(df_g['stock'], errors='coerce').fillna(0)

        # Universo completo (incluye stock negativo, cero y positivo), capturado
        # antes de filtrar por stock > 0, para el panel de "códigos con stock
        # crítico" más abajo.
        df_stock_completo = df_g.copy()

        df_g = df_g[df_g['stock'] > 0]

        total_stock = df_g['stock'].sum()

        if total_stock > 0:
            total_skus_g = len(df_g)
            mensaje_g = (
                f"📦 {int(total_stock):,} unidades en stock | {total_skus_g:,} SKU con stock > 0"
            ).replace(",", ".")
            st.success(mensaje_g)

            import plotly.colors as pc

            def generar_colores_por_ranking(valores, invertir=False):
                """
                Semáforo en degradé: a MAYOR % del total, más VERDE;
                a MENOR %, más ROJO. El color se calcula en proporción real
                al valor de cada porción (no solo por su posición/ranking),
                normalizado dentro del rango min-max de ese mismo gráfico.
                invertir=True da vuelta la lógica (mayor % = más ROJO), útil
                para métricas donde un valor alto es negativo, como Venta 0.
                """
                n = len(valores)
                if n <= 1:
                    # Mismo formato rgb(...) que usa pc.sample_colorscale más abajo,
                    # para que texto_con_contraste pueda parsearlo sin error.
                    return ['rgb(46,125,50)'] if not invertir else ['rgb(183,28,28)']
                v_max, v_min = max(valores), min(valores)
                if v_max == v_min:
                    color_plano = 'rgb(183,28,28)' if invertir else 'rgb(139,195,74)'
                    return [color_plano] * n
                puntos = [(v - v_min) / (v_max - v_min) for v in valores]  # mayor valor -> 1.0 (verde)
                if invertir:
                    puntos = [1 - p for p in puntos]
                return pc.sample_colorscale('RdYlGn', puntos)

            def texto_con_contraste(colores_rgb):
                """
                Elige negro o blanco para el texto de cada porción según qué tan
                clara u oscura sea su color de fondo, para que el % siempre sea
                legible (los tonos claros del degradé, como el amarillo pálido,
                necesitan texto negro; los oscuros necesitan texto blanco).
                """
                resultado = []
                for c in colores_rgb:
                    numeros = re.findall(r'[\d.]+', c)
                    r, g, b = [float(n) for n in numeros[:3]]
                    luminancia = 0.299 * r + 0.587 * g + 0.114 * b
                    resultado.append('#000000' if luminancia > 160 else '#FFFFFF')
                return resultado

            def crear_donut(data, nombre_col, titulo, max_categorias=6, mostrar_vacios=False, invertir_colores=False, umbral_stock=1.0, colores_fijos=None, columna_valor='stock', unidad='unidades', mostrar_conteo_codigos=False):
                # umbral_stock=1.0 por defecto = comportamiento original (solo
                # corta por max_categorias). El corte al 60% de representatividad
                # se activa puntualmente pasando umbral_stock=0.60 (ver gráfico
                # "Stock por Tipo de Producto", que es el único que lo usa).
                # mostrar_vacios=True incluye categorías sin stock (útil para que
                # el gráfico de rango de precio muestre los 6 rangos siempre).
                # colores_fijos={'ETIQUETA': 'rgb(r,g,b)'} fuerza ese color para
                # esa categoría exacta, sin importar el ranking por stock (ej.
                # que "SIN VENTA (0)" siempre se pinte rojo).
                agrupado = data.groupby(nombre_col, observed=not mostrar_vacios)[columna_valor].sum().reset_index()
                agrupado = agrupado.sort_values(columna_valor, ascending=False).reset_index(drop=True)
                # Ya no se agrupa en "OTROS": las categorías menos representativas
                # (baja participación en stock) simplemente se excluyen del gráfico
                # y se listan en un pie de página, en vez de mezclarse en una
                # porción heterogénea que ensucia la torta.
                # Se incluyen categorías (de mayor a menor stock) hasta alcanzar
                # el umbral de representatividad (60% del stock por defecto);
                # nunca menos de 1 ni más que max_categorias.
                excluidos = []
                total_general = agrupado[columna_valor].sum()
                if total_general > 0:
                    acumulado = agrupado[columna_valor].cumsum() / total_general
                    n_incluir = int((acumulado < umbral_stock).sum()) + 1
                    n_incluir = max(1, min(n_incluir, max_categorias, len(agrupado)))
                    if n_incluir < len(agrupado):
                        excluidos = agrupado.iloc[n_incluir:][nombre_col].tolist()
                        agrupado = agrupado.iloc[:n_incluir].reset_index(drop=True)

                if mostrar_conteo_codigos:
                    conteo_serie = data.groupby(nombre_col, observed=not mostrar_vacios).size()
                    agrupado['conteo_codigos'] = agrupado[nombre_col].map(conteo_serie).fillna(0).astype(int)

                colores = generar_colores_por_ranking(agrupado[columna_valor].tolist(), invertir=invertir_colores)
                if colores_fijos:
                    colores = [
                        colores_fijos.get(valor, color)
                        for valor, color in zip(agrupado[nombre_col], colores)
                    ]
                colores_texto = texto_con_contraste(colores)

                # Se agrega el % directamente en el nombre de cada categoría para
                # que la leyenda muestre "NOMBRE (XX.X%)" y sea más fácil de leer.
                total_grupo = agrupado[columna_valor].sum()
                agrupado['etiqueta'] = agrupado.apply(
                    lambda r: f"{r[nombre_col]} ({(r[columna_valor] / total_grupo * 100):.1f}%)", axis=1
                )

                fig = px.pie(
                    agrupado, values=columna_valor, names='etiqueta', hole=0.55,
                    custom_data=['conteo_codigos'] if mostrar_conteo_codigos else None
                )
                # sort=False asegura que el orden de las porciones coincida exactamente
                # con el orden (mayor→menor) usado para calcular los colores.
                fig.update_traces(
                    sort=False,
                    marker=dict(colors=colores, line=dict(color='#FFFFFF', width=2)),
                    textposition='inside',
                    insidetextorientation='horizontal',
                    textinfo='percent',
                    texttemplate='%{percent:.1%}',
                    textfont=dict(size=12, color=colores_texto),
                    hovertemplate=(
                        f'%{{label}}: %{{value:,.0f}} {unidad} / %{{customdata[0]}} códigos (%{{percent}})<extra></extra>'
                        if mostrar_conteo_codigos else
                        f'%{{label}}: %{{value:,.0f}} {unidad} (%{{percent}})<extra></extra>'
                    )
                )
                fig.update_layout(
                    autosize=True,
                    height=380,  # Ya no se reserva espacio abajo para leyenda de Plotly
                    margin=dict(t=50, b=20, l=20, r=20),
                    title=dict(
                        text=titulo,
                        x=0.5,
                        xanchor='center',
                        font=dict(size=14, family="Arial, sans-serif", color="#333333")
                    ),
                    showlegend=False  # La leyenda ahora se dibuja aparte, en grilla de 3 filas
                )

                leyenda_items = list(zip(agrupado['etiqueta'], colores))
                return fig, excluidos, leyenda_items

            def renderizar_leyenda_grid(items, filas=3):
                """
                Dibuja la leyenda como grilla CSS: siempre 'filas' leyendas por
                columna, agregando tantas columnas como haga falta (6 leyendas
                -> 2 columnas de 3; 9 leyendas -> 3 columnas de 3), en vez de
                depender del wrap horizontal de Plotly.
                """
                filas_html = "".join(
                    f'<div style="display:flex;align-items:center;gap:6px;padding:2px 10px;">'
                    f'<span style="width:10px;height:10px;border-radius:2px;background:{color};flex-shrink:0;"></span>'
                    f'<span style="font-size:11px;color:#333;">{etiqueta}</span></div>'
                    for etiqueta, color in items
                )
                st.markdown(
                    f'<div style="display:grid;grid-template-rows:repeat({filas}, auto);'
                    f'grid-auto-flow:column;justify-content:center;">{filas_html}</div>',
                    unsafe_allow_html=True
                )

            # --- Lista dinámica de gráficos a mostrar ---
            # Cada elemento es (data, columna, título, kwargs para crear_donut, nota opcional)
            graficos = []

            # El gráfico "Stock por Línea" se oculta cuando ya se filtró por una línea
            # específica, porque en ese caso mostraría un solo segmento (100%) sin valor.
            if g_linea == "Todas":
                graficos.append((df_g, 'linea', '👕 Stock por Línea', {}, None))

            # Mismo criterio para "Stock por Departamento": se oculta si ya se
            # filtró por un departamento específico.
            if g_depto == "Todos":
                graficos.append((df_g, 'departamento', '🏬 Stock por Departamento', {}, None))

            # Mismo criterio: "Stock por Subcategoría" se oculta si ya se filtró
            # por una subcategoría específica (mostraría un solo segmento).
            # tipos_60: categorías de "tipo de producto" que concentran el 60%
            # del stock de la subcategoría filtrada. Se define solo cuando hay
            # una subcategoría específica seleccionada (ver más abajo);
            # también la usa el gráfico de Stock por Rango de Precio.
            tipos_60 = None

            if g_subcat == "Todas":
                graficos.append((df_g, 'subcategoria', '📦 Stock por Subcategoría', {}, None))
            elif 'descripcion' in df_g.columns:
                df_patron = clasificar_tipo_producto_inteligente(df_g)
                tipos_60 = categorias_representativas(df_patron, 'patron_detectado', max_categorias=9)

                graficos.append((
                    df_patron, 'patron_detectado', '🔎 Stock por Tipo de Producto',
                    {'umbral_stock': 0.60, 'max_categorias': 9}, None
                ))

            # El gráfico "Stock por Temporada" se oculta cuando ya se filtró por
            # una temporada específica, porque en ese caso mostraría un solo
            # segmento (100%) sin valor, igual que Línea/Departamento/Subcategoría.
            if g_temp == "Todas":
                graficos.append((df_g, 'temporada', '🗓️ Stock por Temporada', {}, None))

            df_g['estado_venta'] = df_g[col_venta_mes].apply(
                lambda x: 'CON VENTA' if pd.to_numeric(x, errors='coerce') > 0 else 'SIN VENTA (0)'
            )
            graficos.append((
                df_g, 'estado_venta', '📉 Venta 0 Total',
                {'colores_fijos': {'SIN VENTA (0)': 'rgb(183,28,28)', 'CON VENTA': 'rgb(46,125,50)'}}, None
            ))

            # "Venta 0 por Subcategoría": en realidad agrupa por tipo de producto
            # (mismo patron_detectado que "Stock por Tipo de Producto"), mostrando
            # qué tipos concentran más códigos sin venta este mes. Solo tiene
            # sentido cuando ya hay subcategoría Y temporada filtradas (por eso usa
            # df_patron, que solo existe en esa rama).
            if g_subcat != "Todas" and g_temp != "Todas" and 'patron_detectado' in df_patron.columns:
                df_patron_v0 = df_patron.copy()
                df_patron_v0['estado_venta'] = df_patron_v0[col_venta_mes].apply(
                    lambda x: 'CON VENTA' if pd.to_numeric(x, errors='coerce') > 0 else 'SIN VENTA (0)'
                )
                df_patron_v0['stock_num'] = pd.to_numeric(df_patron_v0['stock'], errors='coerce').fillna(0)
                df_v0_tipo = df_patron_v0[
                    (df_patron_v0['estado_venta'] == 'SIN VENTA (0)') & (df_patron_v0['stock_num'] >= 5)
                ].copy()
                if not df_v0_tipo.empty:
                    graficos.append((
                        df_v0_tipo, 'patron_detectado', '📉 Venta 0 por Subcategoría',
                        {'invertir_colores': True, 'max_categorias': 9, 'mostrar_conteo_codigos': True},
                        "Stock sin venta este mes (stock ≥ 5), por tipo de producto — qué productos concentran el % de Venta 0 Total"
                    ))

            # Desglose por temporada, solo de los productos sin venta (venta 0),
            # para verlo justo al lado del de "Venta 0 Total". Se oculta con el
            # mismo criterio que "Stock por Temporada": si ya se filtró por una
            # temporada específica, mostraría un solo segmento sin valor.
            df_venta0 = df_g[df_g['estado_venta'] == 'SIN VENTA (0)']
            if g_temp == "Todas" and not df_venta0.empty:
                graficos.append((
                    df_venta0, 'temporada', '📉 Venta 0 por Temporada', {'invertir_colores': True},
                    "Muestra participación de solo códigos sin venta este mes"
                ))

            # --- Gráfico de Precios ---
            df_precio = df_g.copy()
            nota_precio = None
            if g_subcat != "Todas" and tipos_60:
                # Al filtrar una subcategoría, el gráfico de precios se calcula
                # solo sobre los tipos de producto que concentran el 60% del
                # stock de esa subcategoría (mismo subconjunto que el gráfico
                # "Stock por Tipo de Producto"), para no diluir la
                # distribución de precios con la larga cola de tipos
                # minoritarios.
                df_precio = df_precio.loc[df_patron['patron_detectado'].isin(tipos_60)]
                nota_precio = "Incluye solo los tipos de producto que concentran el 60% del stock de esta subcategoría"
            df_precio['nuevo precio'] = pd.to_numeric(df_precio['nuevo precio'], errors='coerce').fillna(0)
            df_precio = df_precio[df_precio['nuevo precio'] > 0]
            if not df_precio.empty:
                if g_subcat != "Todas":
                    # Con una subcategoría filtrada se pide el detalle por
                    # precio exacto (ej. "$7.990"), no por rango, para ver
                    # qué precios puntuales concentran el stock.
                    df_precio['precio_exacto'] = df_precio['nuevo precio'].apply(
                        lambda v: f"${v:,.0f}".replace(',', '.')
                    )
                    graficos.append((
                        df_precio, 'precio_exacto', '💲 Stock por Precio',
                        {'umbral_stock': 0.60, 'max_categorias': 9}, nota_precio
                    ))
                else:
                    bins = [0, 9990, 19990, 29990, 39990, 49990, float('inf')]
                    labels = [
                        'Hasta $9.990', '$10.000 - $19.990', '$20.000 - $29.990',
                        '$30.000 - $39.990', '$40.000 - $49.990', '$50.000 y más'
                    ]
                    df_precio['rango_precio'] = pd.cut(
                        df_precio['nuevo precio'], bins=bins, labels=labels, include_lowest=True
                    )
                    # Sin subcategoría filtrada (vista amplia) se mantiene el
                    # desglose por rango, mostrando los 6 rangos completos si
                    # hay un departamento específico seleccionado, o solo los
                    # que concentran stock en la vista general por Línea.
                    graficos.append((
                        df_precio, 'rango_precio', '💲 Stock por Rango de Precio',
                        {'max_categorias': 6, 'mostrar_vacios': g_depto != "Todos"}, None
                    ))

            # --- Renderizado en filas de 3 columnas ---
            etiquetas_campo = {
                'linea': 'línea', 
                'departamento': 'departamento', 
                'subcategoria': 'subcategoría',
                'temporada': 'temporada', 
                'estado_venta': 'estado de venta', 
                'rango_precio': 'rango de precio',
                'precio_exacto': 'precio',
                'patron_detectado': 'tipo de producto'  # <--- AGREGAR ESTA LÍNEA
            }
            for i in range(0, len(graficos), 3):
                fila = graficos[i:i + 3]
                cols = st.columns(len(fila))
                for col, (data_g, campo, titulo, kwargs, nota) in zip(cols, fila):
                    with col:
                        fig, excluidos, leyenda_items = crear_donut(data_g, campo, titulo, **kwargs)
                        st.plotly_chart(fig, use_container_width=True)
                        renderizar_leyenda_grid(leyenda_items)
                        if nota:
                            st.caption(f"ℹ️ {nota}")
                        if excluidos:
                            etiqueta_campo = etiquetas_campo.get(campo, campo)
                            st.caption(
                                f"👁️ En vista la mayor participación de stock de {etiqueta_campo}"
                            )

        else:
            st.warning("⚠️ No se encontró stock disponible para los filtros seleccionados.")

        # --- Panel: Códigos con Stock Crítico (negativo, <5 unidades, en 0) ---
        # Usa df_stock_completo (universo antes del filtro stock > 0) para poder
        # contabilizar también los códigos en negativo y en cero.
        total_codigos = df_stock_completo['producto'].nunique()
        if total_codigos > 0:
            st.markdown("<hr>", unsafe_allow_html=True)
            cod_negativo = df_stock_completo.loc[df_stock_completo['stock'] < 0, 'producto'].nunique()
            cod_menor_5 = df_stock_completo.loc[df_stock_completo['stock'] < 5, 'producto'].nunique()
            cod_cero = df_stock_completo.loc[df_stock_completo['stock'] == 0, 'producto'].nunique()

            df_critico = pd.DataFrame({
                'categoria': ['Stock negativo', 'Stock < 5 unidades', 'Stock en 0'],
                'cantidad': [cod_negativo, cod_menor_5, cod_cero],
            })
            df_critico['pct'] = df_critico['cantidad'] / total_codigos * 100
            df_critico['etiqueta'] = df_critico.apply(
                lambda r: f"{int(r['cantidad']):,} ({r['pct']:.1f}%)".replace(",", "."), axis=1
            )

            fig_critico = px.bar(
                df_critico, x='cantidad', y='categoria', orientation='h',
                text='etiqueta', color='categoria',
                color_discrete_sequence=['#C62828', '#F9A825', '#455A64']
            )
            fig_critico.update_traces(textposition='outside', textfont=dict(size=12), cliponaxis=False)
            fig_critico.update_layout(
                title=dict(
                    text=f"⚠️ Códigos con Stock Crítico (de {total_codigos:,} códigos)".replace(",", "."),
                    x=0.5, xanchor='center',
                    font=dict(size=15, family="Arial, sans-serif", color="#333333")
                ),
                showlegend=False,
                xaxis_title=None, yaxis_title=None,
                margin=dict(t=55, b=10, l=10, r=60),
                height=280,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_critico, use_container_width=True)

    else:
        st.error("No se pudo cargar la base de datos.")

    if st.button("VOLVER AL CONSULTOR DE PRECIOS", use_container_width=True, key="volver_grafico"):
        st.session_state.vista_actual = "escaner"
        st.rerun()

# =======================================================
# --- VISTA 2: INSTRUCTIVOS PDF ---
# =======================================================
elif st.session_state.vista_actual == "instructivos":
    st.title("⚙️ Revisa Catálogos e Instructivos")

    if "tipo_pdf" not in st.session_state:
        st.session_state.tipo_pdf = None
    if "pdf_bytes" not in st.session_state:
        st.session_state.pdf_bytes = None
        st.session_state.pdf_nombre = None

    # --- PASO 1: elegir si es Catálogo o Instructivo ---
    if st.session_state.tipo_pdf is None:
        st.markdown("### Selecciona una opción")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📘 Catálogo", use_container_width=True, key="btn_tipo_catalogo"):
                st.session_state.tipo_pdf = "catalogo"
                st.rerun()
        with col2:
            if st.button("📗 Instructivo", use_container_width=True, key="btn_tipo_instructivo"):
                st.session_state.tipo_pdf = "instructivo"
                st.rerun()

    # --- PASO 2: elegir directamente el PDF entre todos los que hay en Catálogo/Instructivo ---
    elif st.session_state.pdf_bytes is None:
        etiqueta = "Catálogo" if st.session_state.tipo_pdf == "catalogo" else "Instructivo"
        st.markdown(f"#### 📂 Elige el archivo de: {etiqueta}")

        if st.button("🔄 Cambiar tipo (Catálogo/Instructivo)", key="btn_cambiar_tipo"):
            st.session_state.tipo_pdf = None
            st.rerun()

        carpeta_raiz = ID_CARPETA_CATALOGOS if st.session_state.tipo_pdf == "catalogo" else ID_CARPETA_INSTRUCTIVOS

        try:
            with st.spinner("Buscando archivos en Drive..."):
                pdfs = listar_pdfs_recursivo(carpeta_raiz)
        except Exception as e:
            st.error(f"🚨 No se pudo leer la carpeta de Drive. Revisa la API Key y los permisos.\n\nDetalle: {e}")
            pdfs = []

        if not pdfs:
            st.warning("No se encontraron archivos PDF en esta carpeta.")
        else:
            opciones = [f"{p['ruta']} / {p['name']}" if p['ruta'] else p['name'] for p in pdfs]
            seleccion = st.selectbox(
                "Selecciona el PDF a cargar:",
                ["-- Selecciona --"] + opciones,
                key="sel_pdf_directo"
            )
            if seleccion != "-- Selecciona --":
                idx = opciones.index(seleccion)
                elegido = pdfs[idx]
                with st.spinner(f"Cargando '{elegido['name']}'..."):
                    st.session_state.pdf_bytes = descargar_pdf_drive(elegido["id"])
                    st.session_state.pdf_nombre = elegido["name"]
                    st.rerun()

    # --- PASO 3: procesar el PDF ya cargado desde Drive (lógica original, sin cambios) ---
    if st.session_state.pdf_bytes is not None:
        if st.button("🔄 Elegir otro PDF", key="btn_otro_pdf"):
            st.session_state.pdf_bytes = None
            st.session_state.pdf_nombre = None
            st.rerun()

        archivo_pdf_bytes = st.session_state.pdf_bytes
        archivo_pdf_nombre = st.session_state.pdf_nombre

        df_base = cargar_base_precios()
        df_base.columns = df_base.columns.str.strip()
        df_base['PRODUCTO'] = df_base['PRODUCTO'].astype(str)

        doc = fitz.open(stream=archivo_pdf_bytes, filetype="pdf")
        nombre = archivo_pdf_nombre.replace(".pdf", "")
        # Sanitizamos el nombre para evitar problemas de claves
        nombre_limpio = "".join(filter(str.isalnum, nombre))

        pdfs_generados = []  # aquí se junta el PDF de cada hoja para el descargable combinado
        boton_descarga_todo = st.empty()
        st.markdown("<p style='font-size: 16px; font-weight: 600; color: #666; margin-bottom: -5px;'>👇 Selecciona cada hoja del archivo cargado</p>", unsafe_allow_html=True)

        tabs = st.tabs([f":red[Hoja {idx+1}]" for idx in range(len(doc))])

        # Usamos idx_tab para no confundirnos con otros bucles
        for idx_tab, tab in enumerate(tabs):
            with tab:
                page = doc.load_page(idx_tab)

                texto = page.get_text()
                codigos_encontrados = []
                for c in re.findall(r'\b\d{6}\b', texto):
                    if c not in codigos_encontrados:
                        codigos_encontrados.append(c)

                df_res = None
                cols_finales = None
                advertencia_txt = ""
                codigos_inexistentes = []

                if codigos_encontrados:
                    codigos_validos = [c for c in codigos_encontrados if c in df_base['PRODUCTO'].values]
                    codigos_inexistentes = [c for c in codigos_encontrados if c not in df_base['PRODUCTO'].values]

                    if codigos_validos:
                        df_res = df_base.set_index('PRODUCTO').loc[codigos_validos].reset_index()
                        df_res = df_res.rename(columns={'PRODUCTO': 'CODIGO'})
                        mes_actual = datetime.now().strftime('%m')
                        col_mes = f"VENTAS {mes_actual}"
                        df_res['VENTA MES'] = df_res[col_mes] if col_mes in df_res.columns else 0

                        # --- ESTRATEGIA DUAL CORREGIDA (reemplaza todo el bloque anterior) ---
                        import math
                        import re

                        # 1. Obtener imágenes válidas
                        image_list = page.get_images(full=True)
                        imagenes_data = []
                        for img in image_list:
                            rects = page.get_image_rects(img[0])
                            if rects and rects[0].width > 80:
                                r = rects[0]
                                imagenes_data.append({
                                    'rect': r,
                                    'x0': r.x0, 'y0': r.y0, 'x1': r.x1, 'y1': r.y1,
                                    'cx': (r.x0 + r.x1) / 2,
                                    'cy': (r.y0 + r.y1) / 2,
                                    'marcada': False
                                })

                        # 1b. Detectar también las cajas "SIN FOTO" (rectángulos dibujados
                        # sin imagen real embebida). Sin esto, un producto que aún no tiene
                        # foto nunca puede recibir el círculo VTA 0 porque no existe ninguna
                        # "imagen" a la cual asociarlo.
                        def _se_superpone(r1, r2, tol=5):
                            return not (
                                r1[2] < r2[0] - tol or r1[0] > r2[2] + tol or
                                r1[3] < r2[1] - tol or r1[1] > r2[3] + tol
                            )

                        rects_ya_usados = [(i['x0'], i['y0'], i['x1'], i['y1']) for i in imagenes_data]
                        try:
                            dibujos_pagina = page.get_drawings()
                        except Exception:
                            dibujos_pagina = []

                        for d in dibujos_pagina:
                            rect_dibujo = d.get('rect')
                            if rect_dibujo is None:
                                continue
                            if rect_dibujo.width > 80 and rect_dibujo.height > 80:
                                candidato = (rect_dibujo.x0, rect_dibujo.y0, rect_dibujo.x1, rect_dibujo.y1)
                                if not any(_se_superpone(candidato, ru) for ru in rects_ya_usados):
                                    imagenes_data.append({
                                        'rect': rect_dibujo,
                                        'x0': rect_dibujo.x0, 'y0': rect_dibujo.y0,
                                        'x1': rect_dibujo.x1, 'y1': rect_dibujo.y1,
                                        'cx': (rect_dibujo.x0 + rect_dibujo.x1) / 2,
                                        'cy': (rect_dibujo.y0 + rect_dibujo.y1) / 2,
                                        'marcada': False
                                    })
                                    rects_ya_usados.append(candidato)

                        # 2. Detectar layout mirando dónde está el TEXTO con códigos
                        page_width = page.rect.width
                        bloques_texto = page.get_text("blocks")
                        codigos_cero = df_res[
                            (df_res['VENTA MES'] == 0) & (df_res['STOCK'] > 0)
                        ]['CODIGO'].astype(str).tolist()

                        bloques_con_codigo = [b for b in bloques_texto if re.search(r'\b\d{6}\b', b[4])]
                        texto_en_derecha = sum(
                            1 for b in bloques_con_codigo
                            if (b[0] + b[2]) / 2 > page_width * 0.60
                        )
                        es_layout_lateral = (
                            len(bloques_con_codigo) > 0 and
                            texto_en_derecha / len(bloques_con_codigo) >= 0.70
                        )

                        # 3. Función para dibujar el óvalo VTA 0
                        def dibujar_vta0(page, imagen_rect):
                            r = imagen_rect
                            cx = r.x0 + 22
                            cy = r.y0 + 12
                            rect_oval = fitz.Rect(cx - 22, cy - 11, cx + 22, cy + 11)
                            page.draw_oval(rect_oval, color=(1, 0, 0), fill=(1, 0, 0))

                            texto = "VTA 0"
                            fontsize = 9
                            ancho_texto = fitz.get_text_length(texto, fontname="hebo", fontsize=fontsize)
                            texto_x = rect_oval.x0 + (rect_oval.width - ancho_texto) / 2
                            texto_y = rect_oval.y0 + (rect_oval.height + fontsize) / 2 - 1

                            page.insert_text(
                                (texto_x, texto_y),
                                texto,
                                fontsize=fontsize,
                                color=(1, 1, 1),
                                fontname="hebo"
                            )

                        # 4. PRE-PROCESO LAYOUT LATERAL: construir mapa código→imagen
                        # Regla: cada fila tiene 2 imágenes (izq, der) y 2 bloques de texto
                        # ordenados por Y. El 1er bloque → img izq, el 2do → img der
                        mapa_lateral = {}  # {codigo: imagen_data}

                        if es_layout_lateral:
                            # Ordenar imágenes por fila (y0 agrupado) luego por x0 (izq→der)
                            TOLERANCIA_FILA = 50  # px de tolerancia para agrupar imágenes en la misma fila
                            imgs_ordenadas = sorted(imagenes_data, key=lambda img: (round(img['y0'] / TOLERANCIA_FILA), img['x0']))

                            # Agrupar imágenes en filas
                            filas_imgs = []
                            fila_actual = []
                            for img in imgs_ordenadas:
                                if not fila_actual:
                                    fila_actual.append(img)
                                else:
                                    # Si la diferencia de y0 es pequeña, misma fila
                                    if abs(img['y0'] - fila_actual[0]['y0']) < TOLERANCIA_FILA:
                                        fila_actual.append(img)
                                    else:
                                        filas_imgs.append(sorted(fila_actual, key=lambda i: i['x0']))
                                        fila_actual = [img]
                            if fila_actual:
                                filas_imgs.append(sorted(fila_actual, key=lambda i: i['x0']))

                            # Ordenar bloques con código por Y (cy)
                            bloques_ordenados = sorted(bloques_con_codigo, key=lambda b: (b[1] + b[3]) / 2)

                            # Para cada fila de imágenes, asignar los bloques que caen en su rango Y
                            for fila in filas_imgs:
                                fila_y0 = min(img['y0'] for img in fila)
                                fila_y1 = max(img['y1'] for img in fila)
                                margen = (fila_y1 - fila_y0) * 0.3

                                # Bloques cuyo cy cae dentro del rango Y de esta fila
                                bloques_fila = [
                                    b for b in bloques_ordenados
                                    if (fila_y0 - margen) <= (b[1] + b[3]) / 2 <= (fila_y1 + margen)
                                ]
                                # Ordenar bloques de la fila por cy (arriba→abajo)
                                bloques_fila.sort(key=lambda b: (b[1] + b[3]) / 2)

                                # Asignar: bloque[0]→img[0] (izq), bloque[1]→img[1] (der), etc.
                                for idx, b in enumerate(bloques_fila):
                                    if idx < len(fila):
                                        codigos_en_bloque = re.findall(r'\b\d{6}\b', b[4])
                                        for cod in codigos_en_bloque:
                                            mapa_lateral[cod] = fila[idx]

                        # 5. Procesar cada código con venta 0
                        codigos_marcados = set()

                        for c in codigos_cero:

                            if es_layout_lateral:
                                # TIPO B: usar el mapa precalculado
                                if c in mapa_lateral:
                                    img = mapa_lateral[c]
                                    if not img['marcada']:
                                        img['marcada'] = True
                                        dibujar_vta0(page, img['rect'])
                                        codigos_marcados.add(c)

                            else:
                                # TIPO A (grilla): imagen ARRIBA en la misma columna X
                                for b in bloques_texto:
                                    if str(c) not in b[4]:
                                        continue

                                    txt_cx = (b[0] + b[2]) / 2
                                    tolerancia_x = page_width * 0.15
                                    mejor = None
                                    min_score = float('inf')

                                    for img in imagenes_data:
                                        if img['marcada']:
                                            continue
                                        dx = abs(img['cx'] - txt_cx)
                                        dy = b[1] - img['y1']  # distancia base_imagen → tope_texto
                                        if dx < tolerancia_x and -30 < dy < 300:
                                            score = dx * 2 + abs(dy)
                                            if score < min_score:
                                                min_score = score
                                                mejor = img

                                    if mejor:
                                        mejor['marcada'] = True
                                        dibujar_vta0(page, mejor['rect'])
                                        codigos_marcados.add(c)

                                    break  # siguiente código

                        # 6. PASE DE RESPALDO: para los códigos que no calzaron con las reglas
                        # estrictas de arriba (columna exacta / mapa lateral), se les asigna
                        # la imagen o caja "SIN FOTO" libre más cercana a su texto, sin
                        # restricciones de layout. Esto evita dejar productos sin marcar.
                        codigos_pendientes = [c for c in codigos_cero if c not in codigos_marcados]

                        for c in codigos_pendientes:
                            bloque_codigo = next((b for b in bloques_texto if str(c) in b[4]), None)
                            if not bloque_codigo:
                                continue

                            txt_cx = (bloque_codigo[0] + bloque_codigo[2]) / 2
                            txt_cy = (bloque_codigo[1] + bloque_codigo[3]) / 2

                            mejor = None
                            min_dist = float('inf')
                            for img in imagenes_data:
                                if img['marcada']:
                                    continue
                                dist = math.hypot(img['cx'] - txt_cx, img['cy'] - txt_cy)
                                if dist < min_dist:
                                    min_dist = dist
                                    mejor = img

                            # Límite razonable para no asignar a algo lejano y equivocado
                            if mejor and min_dist < page_width * 0.35:
                                mejor['marcada'] = True
                                dibujar_vta0(page, mejor['rect'])
                                codigos_marcados.add(c)

                # Generar PDF
                pix = page.get_pixmap()
                imagen_bytes = pix.tobytes("png")

                if df_res is not None:
                    # ... (Tu lógica de formato de df_res se mantiene igual)
                    if 'NUEVO PRECIO' in df_res.columns:
                        df_res['NUEVO PRECIO'] = pd.to_numeric(df_res['NUEVO PRECIO'], errors='coerce').fillna(0)
                        df_res['NUEVO PRECIO'] = df_res['NUEVO PRECIO'].apply(
                            lambda x: f"$ {int(x):,}".replace(",", ".") if x > 0 else "$ 0"
                        )
                    cols_a_mostrar = ['SUBCATEGORIA', 'CODIGO', 'DESCRIPCION', 'NUEVO PRECIO', 'STOCK', 'VENTA MES']
                    cols_finales = [c for c in cols_a_mostrar if c in df_res.columns]
                    if codigos_inexistentes:
                        advertencia_txt = f"Codigos no encontrados: {', '.join(codigos_inexistentes)}"
                    pdf_data = generar_pdf_completo(imagen_bytes, df_res[cols_finales], f"{nombre} - Hoja {idx_tab+1}", advertencia_txt)
                else:
                    pdf_data = generar_pdf_simple(imagen_bytes, f"{nombre} - Hoja {idx_tab+1}")

                pdfs_generados.append(pdf_data)

                col_titulo, col_boton = st.columns([3, 1])
                with col_titulo:
                    st.markdown(f"<h3 style='color: #ff4b4b;'>Detalle Hoja {idx_tab+1}</h3>", unsafe_allow_html=True)
                with col_boton:
                    st.download_button(
                        label="📥 Descarga en PDF sólo esta hoja",
                        data=pdf_data,
                        file_name=f"{nombre}_hoja_{idx_tab+1}.pdf",
                        mime="application/pdf",
                        key=f"dl_{nombre_limpio}_{idx_tab}" # <--- CLAVE ÚNICA Y SEGURA
                    )

                col_izq, col_der = st.columns([1, 1])
                with col_izq:
                    st.image(imagen_bytes, use_container_width=True)

                with col_der:
                    if df_res is not None:
                        # 1.- Aplica solo negrita a la fila que contenga venta 0 y stock mayor a 0
                        def destacar_venta_cero(row):
                            try:
                                if 'VENTA MES' in row and float(row['VENTA MES']) == 0 and 'STOCK' in row and float(row['STOCK']) > 0:
                                    return ['color: red;'] * len(row)
                            except:
                                pass
                            return [''] * len(row)

                        def alinear_derecha(val):
                            return 'text-align: right;'

                        st.markdown("""
                            <style>
                            [data-testid="stDataFrame"] thead tr th,
                            [data-testid="stDataFrame"] th {
                                color: #ff4b4b !important;
                                font-weight: bold !important;
                            }
                            </style>
                        """, unsafe_allow_html=True)

                        st_tabla = df_res[cols_finales].style\
                            .apply(destacar_venta_cero, axis=1)\
                            .map(alinear_derecha, subset=[c for c in ['NUEVO PRECIO'] if c in df_res.columns])

                        column_config = {
                            "CODIGO": st.column_config.TextColumn("Código", width=60),
                            "DESCRIPCION": st.column_config.TextColumn("Descripción", width=200),
                            "STOCK": st.column_config.NumberColumn("Stock", width=50, format="%d"),
                            "VENTA MES": st.column_config.NumberColumn("Vta. Un.", width=70, format="%d"),
                            "SUBCATEGORIA": st.column_config.TextColumn("Subcategoria", width=100),
                            "NUEVO PRECIO": st.column_config.TextColumn("Precio Hoy", width=73),
                        }

                        st.dataframe(
                            st_tabla,
                            use_container_width=True,
                            hide_index=True,
                            height=(len(df_res) * 35) + 40,
                            column_config=column_config
                        )

                        if codigos_inexistentes:
                            st.markdown("---")
                            st.warning(f"⚠️ Códigos no encontrados: {', '.join(codigos_inexistentes)}")
                    else:
                        if not codigos_encontrados:
                            st.warning("No se detectaron códigos en esta página.")

        if pdfs_generados:
            pdf_combinado = combinar_pdfs(pdfs_generados)
            boton_descarga_todo.download_button(
                label=f"📥 Descargar todo el archivo en PDF",
                data=pdf_combinado,
                file_name=f"{nombre}_completo.pdf",
                mime="application/pdf",
                use_container_width=True,
                key=f"dl_todo_{nombre_limpio}"
            )

    if st.button("⬅️ VOLVER AL CONSULTOR", use_container_width=True):
        st.session_state.vista_actual = "escaner"
        st.session_state.tipo_pdf = None
        st.session_state.pdf_bytes = None
        st.session_state.pdf_nombre = None
        st.rerun()

# =======================================================
# --- VISTA 3: EL ESCÁNER ORIGINAL ---
# =======================================================
elif st.session_state.vista_actual == "escaner":

    manual = ""

    if st.session_state.estado == "esperando":
        if not st.session_state.modo_manual:
            st.markdown("<h3 style='text-align:center; color:#666; font-size:16px;'>APUNTE AL CÓDIGO DE BARRAS</h3>", unsafe_allow_html=True)
            
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
                    const scanner = new Html5Qrcode("reader", { 
                        formatsToSupport: [Html5QrcodeSupportedFormats.EAN_13, Html5QrcodeSupportedFormats.EAN_8, Html5QrcodeSupportedFormats.CODE_128],
                        experimentalFeatures: { useBarCodeDetectorIfSupported: true } 
                    });
                    
                    const config = { 
                        fps: 30, 
                        videoConstraints: { 
                            facingMode: "environment",
                            width: { ideal: 1920 },
                            height: { ideal: 1080 },
                            advanced: [{ focusMode: "continuous" }] 
                        } 
                    };
                    
                    scanner.start({ facingMode: "environment" }, config, (txt) => {
                        const input = window.parent.document.querySelector('input[placeholder="000000000"]');
                        if (input && input.value !== txt) {
                            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                            setter.call(input, txt);
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            if (navigator.vibrate) {
                                navigator.vibrate(200); 
                            }
                            input.focus();
                            setTimeout(() => {
                                input.blur();
                            }, 50);
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
        manual_clean = str(manual).replace("]C1", "").strip()
        sku_6 = manual_clean[:6]
        sku_5 = manual_clean[:5]
        
        df = obtener_datos()
        
        if df is not None:
            res = df[df['producto'] == sku_6]
            sku_match = sku_6
            
            if res.empty:
                res = df[df['producto'] == sku_5]
                sku_match = sku_5
            
            if not res.empty:
                emitir_sonido_ok()
                st.session_state.modo_manual = False
                st.session_state.p = res.iloc[0]
                st.session_state.sku = sku_match
                st.session_state.codigo_completo = manual_clean 
                st.session_state.estado = "resultado"
                st.rerun()
            else:
                st.markdown("""
                    <div style="background-color: #FFEBEE; border: 2px solid #D32F2F; padding: 15px; border-radius: 15px; text-align: center; margin-top: 15px; box-shadow: 0 4px 10px rgba(211,47,47,0.1);">
                        <h4 style="color: #D32F2F; margin: 0; font-weight: 900; font-size: 18px;">⚠️ PRODUCTO NO ENCONTRADO</h4>
                        <p style="color: #D32F2F; margin: 8px 0 0 0; font-size: 14px; font-weight: 600;">Por favor envía una foto de la etiqueta para actualizar la base de datos.</p>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.error("🚨 Error interno: No se pudo conectar con la base de datos. Verifica el archivo de Drive.")

    if st.session_state.estado == "resultado":
        p, sku = st.session_state.p, st.session_state.sku
        
        p_act, p_nue = float(p.get('precio actual', 0)), float(p.get('nuevo precio', 0))
        var, cls = ("🔻 EL PRECIO BAJÓ", "down") if p_nue < p_act else ("🔺 EL PRECIO SUBIÓ", "up") if p_nue > p_act else ("➖ SIN CAMBIO", "same")
        
        obs = str(p.get('observaciones', '')).strip()
        if obs and obs.lower() not in ['nan', 'none', 'null', '']:
            html_obs = f'<div style="margin-top: 15px; padding: 12px; background-color: #FFF3E0; border-left: 5px solid #FF9800; color: #E65100; border-radius: 8px; font-size: 14px; font-weight: 700; text-align: left;">⚠️ OBS: {obs.upper()}</div>'
        else:
            html_obs = f'<div style="margin-top: 15px; padding: 12px; background-color: #F1F5F9; border-left: 5px solid #94A3B8; color: #64748B; border-radius: 8px; font-size: 14px; font-weight: 700; text-align: left;">✅ SIN OBSERVACIONES</div>'

        try:
            stock_disp = int(float(p.get('stock', 0))) 
        except:
            stock_disp = 0
            
        color_txt_stock = "#1E40AF" if stock_disp > 0 else "#B91C1C"
        color_bg_stock = "#DBEAFE" if stock_disp > 0 else "#FEE2E2"
        icono_stock = "📦" if stock_disp > 0 else "🚫"
        html_stock = f'<div style="margin-top: 10px; padding: 10px; background-color: {color_bg_stock}; color: {color_txt_stock}; border-radius: 8px; font-size: 20px; font-weight: 900;">{icono_stock} STOCK DISPONIBLE: {stock_disp}</div>'

        col_venta_mes = f"ventas {datetime.now().strftime('%m')}"
        try:
            ventas_mes = int(pd.to_numeric(p.get(col_venta_mes, 0), errors='coerce'))
        except:
            ventas_mes = 0
            
        color_txt_ventas = "#B91C1C" if ventas_mes == 0 else "#1E40AF"
        color_bg_ventas = "#FEE2E2" if ventas_mes == 0 else "#DBEAFE"
        icono_ventas = "📉" if ventas_mes == 0 else "💰"
        html_ventas = f'<div style="margin-top: 5px; padding: 10px; background-color: {color_bg_ventas}; color: {color_txt_ventas}; border-radius: 8px; font-size: 20px; font-weight: 900;">{icono_ventas} UNIDADES VENDIDAS: {ventas_mes}</div>'

        codigo_9 = st.session_state.get('codigo_completo', p.get('producto', ''))

        tarjeta_html = f'<div class="product-card"><div class="product-title">{str(p.get("descripcion", "PRODUCTO")).upper()}</div><div style="font-size: 15px; color: #64748b; font-weight: 700; margin-bottom: 2px; text-transform: uppercase; letter-spacing: 0.5px;">{str(p.get("departamento", "SIN DEPTO"))} | {str(p.get("subcategoria", "SIN CATEGORIA"))}</div><div style="font-size: 13px; color: #94a3b8; font-weight: 700; margin-bottom: 15px; text-transform: uppercase; letter-spacing: 0.5px;">TEMPORADA: {str(p.get("temporada", "SIN TEMPORADA")).upper()}</div><div class="price-value">$ {p_nue:,.0f}</div><div class="trend-pill {cls}">{var}</div>{html_obs}{html_stock}{html_ventas}<div style="margin-top:25px; color:#444; font-size:18px; font-weight: 900; letter-spacing: 3px;">{codigo_9}</div><div style="margin-top:5px; color:#999; font-size:12px;">SKU BASE: {sku}</div></div>'
        
        st.markdown(tarjeta_html.replace(',', '.'), unsafe_allow_html=True)

        if st.button("🔄 CONSULTAR OTRO PRODUCTO", use_container_width=True):
            st.session_state.estado = "esperando"
            st.rerun()