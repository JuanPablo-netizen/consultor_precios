import streamlit as st
import pandas as pd
import requests
import io
import re
import fitz
from fpdf import FPDF
from datetime import datetime

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

def generar_pdf_simple(image_bytes, titulo):
    pdf = FPDF(orientation='L', unit='mm', format='Letter')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, titulo, ln=True, align='C')
    pdf.ln(5)
    pdf.image(io.BytesIO(image_bytes), x=10, y=25, w=250, type='PNG')
    return bytes(pdf.output(dest='S'))

def generar_pdf_completo(image_bytes, df, titulo, advertencias=""):
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
    col_widths = [20, 80, 30, 30, 15, 25, 25, 25] # <-- Se agrega un 25 extra al final
    anchos_reales = col_widths[:len(df.columns)]  # <-- Nueva línea para saber cuántas columnas hay
    total_width = sum(anchos_reales)              # <-- Suma dinámica
    x_start = (279.4 - total_width) / 2  # Centrado basado en ancho Letter Landscape (279.4 mm)

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

    st.markdown("---")
    st.markdown("### ⏰ Gestiona Instructivos y Catálogos")
    if st.button("⚙️ Procesa Stock Instructivos y Catálogos", use_container_width=True):
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

        f2_c1, f2_c2, f2_c3 = st.columns(3)
        with f2_c1:
            lista_temp = sorted([str(x) for x in df_s['temporada'].unique() if str(x) != "SIN DATO"])
            f_temp = st.selectbox("Temporada", ["Todas"] + lista_temp)
        with f2_c2:
            f_venta_cero = st.selectbox("Filtrar Venta 0", ["Ambos", "Solo Venta 0", "Solo con Venta"])
        with f2_c3:
            lista_precios = sorted([float(x) for x in df_s['nuevo precio'].unique() if pd.to_numeric(x, errors='coerce') > 0])
            f_precio = st.selectbox("Precio", ["Todos"] + lista_precios, format_func=lambda x: f"${int(x):,}".replace(",", ".") if x != "Todos" else x)

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            f_pareto = st.checkbox("80% del Stock")
        with col_c2:
            f_obs_only = st.checkbox("Solo con Observaciones")
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
        
        if f_obs_only:
            df_mostrar = df_mostrar[
                (df_mostrar['observaciones'].notna()) & 
                (df_mostrar['observaciones'].astype(str).str.upper() != 'SIN DATO') &
                (df_mostrar['observaciones'].astype(str).str.lower() != 'nan')
            ]
        
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
            pct_v0 = (skus_venta_0 / total_skus) * 100
            pct_con_v = (skus_con_venta / total_skus) * 100
            mensaje_metricas = (
                f"🔍 {skus_venta_0:,} SKU venta 0 ({pct_v0:.1f}%) | "
                f"{skus_con_venta:,} SKU con venta ({pct_con_v:.1f}%) - Mes en Curso (Dato no considera Stock menor o igual a 0)"
            ).replace(',', '.')
            if pct_v0 > 40:
                st.error(mensaje_metricas)
            else:
                st.success(mensaje_metricas)

            mapa_columnas = {
                'producto': 'PRODUCTO', 'descripcion': 'DESCRIPCIÓN', 'marca': 'MARCA',
                'temporada': 'TEMPORADA', 'stock': 'STOCK', 'nuevo precio': 'PRECIO',
                col_venta_mes: 'U. VENDIDAS'
            }
            df_vista = df_mostrar[[c for c in mapa_columnas.keys() if c in df_mostrar.columns]].rename(columns=mapa_columnas)
            df_vista['STOCK'] = pd.to_numeric(df_vista['STOCK'], errors='coerce').fillna(0).astype(int)
            df_vista['PRECIO'] = pd.to_numeric(df_vista['PRECIO'], errors='coerce').fillna(0)
            df_vista['U. VENDIDAS'] = pd.to_numeric(df_vista['U. VENDIDAS'], errors='coerce').fillna(0).astype(int)
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
                df_pdf = df_vista.copy()
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
# --- VISTA 2: INSTRUCTIVOS PDF ---
# =======================================================
elif st.session_state.vista_actual == "instructivos":
    st.title("⚙️ Procesa Stock de Instructivos y Catalogos")

    archivo_pdf = st.file_uploader("Sube tu archivo PDF", type="pdf", key="uploader_unico")

    if archivo_pdf:
        df_base = cargar_base_precios()
        df_base.columns = df_base.columns.str.strip()
        df_base['PRODUCTO'] = df_base['PRODUCTO'].astype(str)

        doc = fitz.open(stream=archivo_pdf.read(), filetype="pdf")
        nombre = archivo_pdf.name.replace(".pdf", "")
        # Sanitizamos el nombre para evitar problemas de claves
        nombre_limpio = "".join(filter(str.isalnum, nombre))

        st.markdown("<p style='font-size: 16px; font-weight: 600; color: #666; margin-bottom: -5px;'>👇 Selecciona cada hoja para ver los stock</p>", unsafe_allow_html=True)

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
                        for c in codigos_cero:

                            if es_layout_lateral:
                                # TIPO B: usar el mapa precalculado
                                if c in mapa_lateral:
                                    img = mapa_lateral[c]
                                    if not img['marcada']:
                                        img['marcada'] = True
                                        dibujar_vta0(page, img['rect'])

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

                                    break  # siguiente código

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

                col_titulo, col_boton = st.columns([3, 1])
                with col_titulo:
                    st.markdown(f"<h3 style='color: #ff4b4b;'>Detalle Hoja {idx_tab+1}</h3>", unsafe_allow_html=True)
                with col_boton:
                    st.download_button(
                        label="📥 Descargarlo en PDF",
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
    if st.button("⬅️ VOLVER AL CONSULTOR", use_container_width=True):
        st.session_state.vista_actual = "escaner"
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

        tarjeta_html = f'<div class="product-card"><div class="product-title">{str(p.get("descripcion", "PRODUCTO")).upper()}</div><div style="font-size: 15px; color: #64748b; font-weight: 700; margin-bottom: 15px; text-transform: uppercase; letter-spacing: 0.5px;">{str(p.get("departamento", "SIN DEPTO"))} | {str(p.get("subcategoria", "SIN CATEGORIA"))}</div><div class="price-value">$ {p_nue:,.0f}</div><div class="trend-pill {cls}">{var}</div>{html_obs}{html_stock}{html_ventas}<div style="margin-top:25px; color:#444; font-size:18px; font-weight: 900; letter-spacing: 3px;">{codigo_9}</div><div style="margin-top:5px; color:#999; font-size:12px;">SKU BASE: {sku}</div></div>'
        
        st.markdown(tarjeta_html.replace(',', '.'), unsafe_allow_html=True)

        if st.button("🔄 CONSULTAR OTRO PRODUCTO", use_container_width=True):
            st.session_state.estado = "esperando"
            st.rerun()