import streamlit as st
import pandas as pd
import requests
import io
from fpdf import FPDF

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
    st.components.v1.html("""
        <script>
        const monitor = setInterval(() => {
            const input = window.parent.document.querySelector('input[placeholder="000000000"]');
            if (input && input.value.length >= 9) {
                clearInterval(monitor); // Detiene el monitor
                
                // 📳 HACE VIBRAR EL TELÉFONO (Android)
                if (navigator.vibrate) {
                    navigator.vibrate(200); // 200 milisegundos
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
        # Usamos tu configuración original que funcionaba
        df = pd.read_excel(io.BytesIO(r.content), engine='calamine')
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.rename(columns={'articulo': 'producto', 'artículo': 'producto', 'codigo': 'producto', 'descripción': 'descripcion'})
        
        # --- BLINDAJE CONTRA EL ".0" ---
        df['producto'] = pd.to_numeric(df['producto'], errors='coerce')
        df = df.dropna(subset=['producto'])
        df['producto'] = df['producto'].astype('int64').astype(str).str.strip()
        
        return df
    except Exception as e:
        # ESTO ES NUEVO: Mostrará el error técnico real en pantalla
        st.error(f"⚠️ Error técnico detallado: {e}")
        return None

# --- 5.5 BOTÓN DE SINCRONIZACIÓN MANUAL ---
with st.sidebar:
    st.markdown("### ⚙️ Administración")
    st.info("Usa este botón para descargar inmediatamente los precios más recientes desde Drive.")
    if st.button("🔄 Sincronizar Base de Precios", use_container_width=True):
        st.cache_data.clear()  # Esto borra la memoria de 12 horas
        st.success("✅ Memoria borrada. Cargando nuevos datos...")
        import time
        time.sleep(1)
        st.rerun()

    # 👇 AGREGA ESTE BLOQUE 👇
    st.markdown("---")
    st.markdown("### 📋 Consultas Masivas")
    if st.button("📦 Ver Listado de Stock", use_container_width=True):
        st.session_state.vista_actual = "listado"
        st.rerun()

# --- 6. INTERFAZ Y FLUJO ---
if "estado" not in st.session_state: st.session_state.estado = "esperando"
if "modo_manual" not in st.session_state: st.session_state.modo_manual = False
# 👇 AGREGA ESTA LÍNEA 👇
if "vista_actual" not in st.session_state: st.session_state.vista_actual = "escaner"

# =======================================================
# --- VISTA 1: LISTADO DE STOCK (VERSIÓN LIMPIA Y ESPACIADA) ---
# =======================================================
class PDF(FPDF):
    def __init__(self, depto, sub, venta):
        super().__init__(orientation='L', unit='mm', format='A4')
        self.depto = depto
        self.sub = sub
        self.venta = venta
        self.alias_nb_pages()

    def header(self):
        # Título
        self.set_font("Arial", 'B', 16)
        self.cell(0, 10, "Reporte de Stock - Consultor Curico", ln=True, align='C')
        # Filtros
        self.set_font("Arial", 'I', 9)
        self.cell(0, 6, f"Filtros: Depto: {self.depto} | Subcategoría: {self.sub} | Venta: {self.venta}", ln=True, align='C')
        # Paginación
        self.set_font("Arial", 'I', 8)
        self.cell(0, -10, f"Pag {self.page_no()}/{{nb}}", align='R')
        self.ln(10)
        # Encabezados de tabla
        self.set_fill_color(200, 200, 200)
        self.set_font("Arial", 'B', 8)
        self.cols = ['PRODUCTO', 'DESCRIPCIÓN', 'MARCA', 'TEMPORADA', 'STOCK', 'PRECIO', 'U. VENDIDAS']
        self.widths = [25, 90, 35, 40, 20, 25, 25] 
        for i, col in enumerate(self.cols):
            self.cell(self.widths[i], 8, col, 1, 0, 'C', fill=True)
        self.ln()

def generar_pdf(df, depto, sub, venta):
    pdf = PDF(depto, sub, venta)
    pdf.add_page()
    pdf.set_font("Arial", '', 9)
    for _, row in df.iterrows():
        # Formato Moneda
        try: p = f"$ {int(float(row.get('PRECIO', 0))):,}".replace(",", ".")
        except: p = "$ 0"
        
        pdf.cell(pdf.widths[0], 8, str(row.get('PRODUCTO', '')), 1, 0, 'C')
        pdf.cell(pdf.widths[1], 8, str(row.get('DESCRIPCIÓN', '')), 1, 0, 'L')
        pdf.cell(pdf.widths[2], 8, str(row.get('MARCA', '')), 1, 0, 'C')
        pdf.cell(pdf.widths[3], 8, str(row.get('TEMPORADA', '')), 1, 0, 'C')
        pdf.cell(pdf.widths[4], 8, str(row.get('STOCK', '')), 1, 0, 'C')
        pdf.cell(pdf.widths[5], 8, p, 1, 0, 'C')
        pdf.cell(pdf.widths[6], 8, str(row.get('U. VENDIDAS', '')), 1, 0, 'C')
        pdf.ln()
    return bytes(pdf.output(dest='S'))

if st.session_state.vista_actual == "listado":
    st.markdown("<h3 style='text-align: center; color: #D32F2F; font-weight: 900;'>📦 BÚSQUEDA DE STOCK</h3>", unsafe_allow_html=True)
    
    df_raw = obtener_datos()
    
    if df_raw is not None:
        df = df_raw.copy()
        
        # 1. LÓGICA DE TIEMPO
        from datetime import datetime
        hoy = datetime.now()
        col_venta_mes = f"ventas {hoy.strftime('%m')}" 

        # 2. LIMPIEZA GLOBAL (Soluciona TypeError de la imagen 3)
        cols_texto = ['linea', 'departamento', 'subcategoria', 'temporada', 'marca']
        for c in cols_texto:
            df[c] = df[c].astype(str).str.strip().str.upper().replace(['NAN', 'NONE', 'N/A', ''], 'SIN DATO')

        # 3. FILTROS (Fila 1)
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

        # 4. FILTROS (Fila 2)
        f2_c1, f2_c2, f2_c3 = st.columns(3)
        with f2_c1:
            lista_temp = sorted([str(x) for x in df_s['temporada'].unique() if str(x) != "SIN DATO"])
            f_temp = st.selectbox("Temporada", ["Todas"] + lista_temp)
        with f2_c2:
            f_venta_cero = st.selectbox("Filtrar Venta", ["Ambos", "Solo Venta 0", "Solo con Venta"])
        with f2_c3:
            lista_precios = sorted([float(x) for x in df_s['nuevo precio'].unique() if pd.to_numeric(x, errors='coerce') > 0])
            f_precio = st.selectbox("Precio", ["Todos"] + lista_precios, format_func=lambda x: f"${int(x):,}".replace(",", ".") if x != "Todos" else x)
            # 4.5 FILTRO DE VISTA PARETO / OBSERVACIONES
        # 4.5 NUEVOS FILTROS COMBINABLES
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            f_pareto = st.checkbox("80% del Stock")
        with col_c2:
            f_obs_only = st.checkbox("Solo con Observaciones")

        # 5. APLICACIÓN DE FILTROS
        df_mostrar = df_s.copy()
        if f_temp != "Todas": df_mostrar = df_mostrar[df_mostrar['temporada'] == f_temp]
        if f_marca != "Todas": df_mostrar = df_mostrar[df_mostrar['marca'] == f_marca]
        if f_precio != "Todos": df_mostrar = df_mostrar[df_mostrar['nuevo precio'] == f_precio]
        
        if f_venta_cero == "Solo Venta 0":
            df_mostrar = df_mostrar[df_mostrar[col_venta_mes] == 0]
        elif f_venta_cero == "Solo con Venta":
            df_mostrar = df_mostrar[df_mostrar[col_venta_mes] > 0]
        
        # --- LÓGICA DE FILTRADO COMBINABLE (PARETO Y OBSERVACIONES) ---
        
        # 1. Filtro de Observaciones (se aplica primero)
        if f_obs_only:
            df_mostrar = df_mostrar[
                (df_mostrar['observaciones'].notna()) & 
                (df_mostrar['observaciones'].astype(str).str.upper() != 'SIN DATO') &
                (df_mostrar['observaciones'].astype(str).str.lower() != 'nan')
            ]
        
        # 2. Filtro Pareto 80% (se aplica sobre el resultado anterior)
        if f_pareto:
            df_mostrar = df_mostrar.sort_values(by='stock', ascending=False)
            total_st = df_mostrar['stock'].sum()
            
            if total_st > 0:
                df_mostrar['cum_stock'] = df_mostrar['stock'].cumsum()
                df_mostrar = df_mostrar[df_mostrar['cum_stock'] <= (0.8 * total_st)]
                df_mostrar = df_mostrar.drop(columns=['cum_stock'])

        # 6. CÁLCULO DE MÉTRICAS Y TABLA ÚNICA
        total_skus = len(df_mostrar)
        if total_skus > 0:
            skus_con_venta = len(df_mostrar[df_mostrar[col_venta_mes] > 0])
            skus_venta_0 = total_skus - skus_con_venta
            
            pct_v0 = (skus_venta_0 / total_skus) * 100
            pct_con_v = (skus_con_venta / total_skus) * 100
            
            mensaje_metricas = (
                f"🔍 {skus_venta_0:,} SKU venta 0 ({pct_v0:.1f}%) | "
                f"{skus_con_venta:,} SKU con venta ({pct_con_v:.1f}%) - Mes en Curso"
            ).replace(',', '.')
            
            # Condición de color: mayor a 40% pinta rojo (st.error), de lo contrario verde (st.success)
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

            # 7. TOTALES, ESPACIADOR Y BOTÓN PDF
            t_stock = int(df_vista['STOCK'].sum())
            
            # Usamos columnas para poner el total a la izquierda y el botón a la derecha
            col_t1, col_t2 = st.columns([2, 1])
            
            with col_t1:
                st.markdown(f"""
                    <div style='background-color:#FEE2E2;padding:10px;border-radius:10px;text-align:center;border:2px solid #D32F2F;margin-bottom:10px;'>
                        <span style='color:#D32F2F;font-weight:900;font-size:18px;'>TOTAL STOCK FILTRADO: {t_stock:,}</span>
                    </div>
                """.replace(',', '.'), unsafe_allow_html=True)
            
            with col_t2:
                # Generamos el PDF con los argumentos necesarios
                pdf_bytes = generar_pdf(df_vista, f_depto, f_sub, f_venta_cero)
                
                st.download_button(
                    label="📥 Descargar PDF",
                    data=pdf_bytes,
                    file_name=f"Stock_Curico_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            
            # Separador visual extra
            st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

        else:
            st.warning("⚠️ No se encontraron productos.")

        if st.button("VOLVER AL CONSULTOR DE PRECIOS", use_container_width=True):
            st.session_state.vista_actual = "escaner"
            st.rerun()
    else:
        st.error("No se pudo cargar la base de datos.")

# =======================================================
# --- VISTA 2: EL ESCÁNER ORIGINAL (Se oculta si estás en el listado) ---
# =======================================================
elif st.session_state.vista_actual == "escaner":

    # 👇 CAMBIO QUIRÚRGICO: Declaramos la variable vacía por defecto para evitar el NameError 👇
    manual = ""

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
                    
                    // PARCHE iOS: Intentar forzar autofocus y mejorar el campo de visión
                    const config = { 
                        fps: 30, 
                        // Quitamos aspectRatio: 1.0 para que el iPhone use todo el sensor sin recortar
                        videoConstraints: { 
                            facingMode: "environment",
                            width: { ideal: 1920 }, // Subimos a Full HD para compensar la falta de enfoque
                            height: { ideal: 1080 },
                            // Truco para pedirle a Safari que intente enfocar automáticamente
                            advanced: [{ focusMode: "continuous" }] 
                        } 
                    };
                    
                    scanner.start({ facingMode: "environment" }, config, (txt) => {
                        const input = window.parent.document.querySelector('input[placeholder="000000000"]');
                        if (input && input.value !== txt) {
                            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                            setter.call(input, txt);
                            
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            
                            // 📳 HACE VIBRAR EL TELÉFONO AL ESCANEAR (Android)
                            if (navigator.vibrate) {
                                navigator.vibrate(200); 
                            }
                            
                            input.focus();
                            setTimeout(() => {
                                input.blur(); // Gatilla la búsqueda
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
        # 1. Omitir caracteres ]C1 y limpiar la entrada
        manual_clean = str(manual).replace("]C1", "").strip()
        
        # 2. Rescatar los primeros 6 y 5 dígitos
        sku_6 = manual_clean[:6]
        sku_5 = manual_clean[:5]
        
        df = obtener_datos()
        
        if df is not None:
            # 3. Buscar primero por 6 dígitos; si no hay resultados, intentar con 5
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
                # Guardamos el código completo limpio (sin el ]C1) para mostrarlo en pantalla
                st.session_state.codigo_completo = manual_clean 
                st.session_state.estado = "resultado"
                st.rerun()
            else:
                # --- EL CÓDIGO NO EXISTE EN EL EXCEL ---
                st.markdown("""
                    <div style="background-color: #FFEBEE; border: 2px solid #D32F2F; padding: 15px; border-radius: 15px; text-align: center; margin-top: 15px; box-shadow: 0 4px 10px rgba(211,47,47,0.1);">
                        <h4 style="color: #D32F2F; margin: 0; font-weight: 900; font-size: 18px;">⚠️ PRODUCTO NO ENCONTRADO</h4>
                        <p style="color: #D32F2F; margin: 8px 0 0 0; font-size: 14px; font-weight: 600;">Por favor envía una foto de la etiqueta para actualizar la base de datos.</p>
                    </div>
                """, unsafe_allow_html=True)
        else:
            # --- ERROR AL CARGAR EL EXCEL DE DRIVE ---
            st.error("🚨 Error interno: No se pudo conectar con la base de datos. Verifica el archivo de Drive.")

    # ==========================================================
    # --- PANTALLA DE RESULTADO (AHORA DENTRO DEL ESCÁNER) ---
    # ==========================================================
    if st.session_state.estado == "resultado":
        p, sku = st.session_state.p, st.session_state.sku
        
        # 1. PRECIOS Y TENDENCIA
        p_act, p_nue = float(p.get('precio actual', 0)), float(p.get('nuevo precio', 0))
        var, cls = ("🔻 EL PRECIO BAJÓ", "down") if p_nue < p_act else ("🔺 EL PRECIO SUBIÓ", "up") if p_nue > p_act else ("➖ SIN CAMBIO", "same")
        
        # 2. OBSERVACIONES
        obs = str(p.get('observaciones', '')).strip()
        if obs and obs.lower() not in ['nan', 'none', 'null', '']:
            html_obs = f'<div style="margin-top: 15px; padding: 12px; background-color: #FFF3E0; border-left: 5px solid #FF9800; color: #E65100; border-radius: 8px; font-size: 14px; font-weight: 700; text-align: left;">⚠️ OBS: {obs.upper()}</div>'
        else:
            html_obs = f'<div style="margin-top: 15px; padding: 12px; background-color: #F1F5F9; border-left: 5px solid #94A3B8; color: #64748B; border-radius: 8px; font-size: 14px; font-weight: 700; text-align: left;">✅ SIN OBSERVACIONES</div>'

        # --- 2.5 BLOQUE DE STOCK ---
        try:
            stock_disp = int(float(p.get('stock', 0))) 
        except:
            stock_disp = 0
            
        color_txt_stock = "#1E40AF" if stock_disp > 0 else "#B91C1C"
        color_bg_stock = "#DBEAFE" if stock_disp > 0 else "#FEE2E2"
        icono_stock = "📦" if stock_disp > 0 else "🚫"
        html_stock = f'<div style="margin-top: 10px; padding: 10px; background-color: {color_bg_stock}; color: {color_txt_stock}; border-radius: 8px; font-size: 20px; font-weight: 900;">{icono_stock} STOCK DISP: {stock_disp}</div>'

        # --- 2.6 BLOQUE DE VENTAS MES ACTUAL (NUEVO) ---
        from datetime import datetime
        col_venta_mes = f"ventas {datetime.now().strftime('%m')}"
        try:
            ventas_mes = int(pd.to_numeric(p.get(col_venta_mes, 0), errors='coerce'))
        except:
            ventas_mes = 0
            
        # Lógica de color: Rojo si es 0, Azul oscuro si tiene ventas
        color_txt_ventas = "#B91C1C" if ventas_mes == 0 else "#1E40AF"
        color_bg_ventas = "#FEE2E2" if ventas_mes == 0 else "#DBEAFE"
        icono_ventas = "📉" if ventas_mes == 0 else "💰"
        html_ventas = f'<div style="margin-top: 5px; padding: 10px; background-color: {color_bg_ventas}; color: {color_txt_ventas}; border-radius: 8px; font-size: 20px; font-weight: 900;">{icono_ventas} VENTAS MES: {ventas_mes}</div>'

        # 3. RESCATE DE CÓDIGO 9 DÍGITOS
        codigo_9 = st.session_state.get('codigo_completo', p.get('producto', ''))

        # 4. HTML DE LA TARJETA (Incluye html_ventas)
        tarjeta_html = f'<div class="product-card"><div class="product-title">{str(p.get("descripcion", "PRODUCTO")).upper()}</div><div style="font-size: 15px; color: #64748b; font-weight: 700; margin-bottom: 15px; text-transform: uppercase; letter-spacing: 0.5px;">{str(p.get("departamento", "SIN DEPTO"))} | {str(p.get("subcategoria", "SIN CATEGORIA"))}</div><div class="price-value">$ {p_nue:,.0f}</div><div class="trend-pill {cls}">{var}</div>{html_obs}{html_stock}{html_ventas}<div style="margin-top:25px; color:#444; font-size:18px; font-weight: 900; letter-spacing: 3px;">{codigo_9}</div><div style="margin-top:5px; color:#999; font-size:12px;">SKU BASE: {sku}</div></div>'
        
        st.markdown(tarjeta_html.replace(',', '.'), unsafe_allow_html=True)

        if st.button("🔄 CONSULTAR OTRO PRODUCTO", use_container_width=True):
            st.session_state.estado = "esperando"
            st.rerun()