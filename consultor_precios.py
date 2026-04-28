import streamlit as st
import pandas as pd
import requests
import io

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
# --- VISTA 1: LISTADO DE STOCK CON FILTROS AVANZADOS ---
# =======================================================
if st.session_state.vista_actual == "listado":
    st.markdown("<h3 style='text-align: center; color: #D32F2F; font-weight: 900;'>📦 BÚSQUEDA DE STOCK</h3>", unsafe_allow_html=True)
    
    if st.button("📷 VOLVER AL ESCÁNER", use_container_width=True):
        st.session_state.vista_actual = "escaner"
        st.rerun()
        
    df = obtener_datos()
    
    if df is not None:
        # Asegurarnos de que las columnas existan, incluyendo 'venta total'
        cols_req = ['linea', 'departamento', 'subcategoria', 'temporada', 'nuevo precio', 'stock', 'venta total']
        for c in cols_req:
            if c not in df.columns: 
                df[c] = 0 if c in ['nuevo precio', 'stock', 'venta total'] else "N/A"
                
        # Limpiar numéricos
        df['nuevo precio'] = pd.to_numeric(df['nuevo precio'], errors='coerce').fillna(0)
        df['venta total'] = pd.to_numeric(df['venta total'], errors='coerce').fillna(0)
        
        st.markdown("---")
        
        # --- BLOQUE ARRIBA: Linea - Departamento - Subcategoria ---
        f_col1, f_col2, f_col3 = st.columns(3)
        
        with f_col1:
            lista_lineas = sorted([str(x) for x in df['linea'].unique() if pd.notna(x) and x != "N/A"])
            f_linea = st.selectbox("Línea", ["Todas"] + lista_lineas)
            
        with f_col2:
            # Estandarizamos el texto
            df['departamento'] = df['departamento'].astype(str).str.strip().str.upper()
            df_filtro_depto = df if f_linea == "Todas" else df[df['linea'] == f_linea]
            
            # Forzamos str(x) para evitar el choque entre textos y números nulos
            lista_deptos = sorted([str(x) for x in df_filtro_depto['departamento'].unique() if str(x).upper() not in ["N/A", "NAN", ""]])
            f_depto = st.selectbox("Departamento", ["Todos"] + lista_deptos)
            
        with f_col3:
            # Aplicamos la misma estandarización y protección a la subcategoría
            df['subcategoria'] = df['subcategoria'].astype(str).str.strip().str.upper()
            df_filtro_sub = df_filtro_depto if f_depto == "Todos" else df_filtro_depto[df_filtro_depto['departamento'] == f_depto]
            
            lista_subs = sorted([str(x) for x in df_filtro_sub['subcategoria'].unique() if str(x).upper() not in ["N/A", "NAN", ""]])
            f_sub = st.selectbox("Subcategoría", ["Todas"] + lista_subs)
            
        # --- BLOQUE ABAJO: Temporada - Venta 0 - Precio ---
        b_col1, b_col2, b_col3 = st.columns(3)
        
        with b_col1:
            # Estandarizamos el texto (todo mayúscula y sin espacios extra)
            df['temporada'] = df['temporada'].astype(str).str.strip().str.upper()
            
            # Simplificamos INV. a INVIERNO y VER. a VERANO
            df['temporada'] = df['temporada'].replace({'INV.': 'INVIERNO', 'VER.': 'VERANO'})
            
            # Filtramos los nulos o vacíos que hayan quedado
            lista_temp = sorted([x for x in df['temporada'].unique() if x not in ["N/A", "NAN", ""]])
            f_temp = st.selectbox("Temporada", ["Todas"] + lista_temp)
            
        with b_col2:
            f_venta_cero = st.selectbox("Venta 0", ["Ambos", "Sí", "No"])
            
        with b_col3:
            lista_precios = sorted([float(x) for x in df['nuevo precio'].unique() if pd.notna(x)])
            
            # Función interna para formatear la vista del selector
            def formato_precio_cl(val):
                if val == "Todos": 
                    return val
                return f"${int(val):,}".replace(",", ".")
                
            f_precio = st.selectbox("Precio", ["Todos"] + lista_precios, format_func=formato_precio_cl)

        # --- APLICAR FILTROS ---
        df_mostrar = df.copy()
        
        if f_linea != "Todas": df_mostrar = df_mostrar[df_mostrar['linea'] == f_linea]
        if f_depto != "Todos": df_mostrar = df_mostrar[df_mostrar['departamento'] == f_depto]
        if f_sub != "Todas": df_mostrar = df_mostrar[df_mostrar['subcategoria'] == f_sub]
        if f_temp != "Todas": df_mostrar = df_mostrar[df_mostrar['temporada'] == f_temp]
        
        if f_venta_cero == "Sí":
            df_mostrar = df_mostrar[df_mostrar['venta total'] == 0]
        elif f_venta_cero == "No":
            df_mostrar = df_mostrar[df_mostrar['venta total'] > 0]
            
        if f_precio != "Todos":
            df_mostrar = df_mostrar[df_mostrar['nuevo precio'] == f_precio]
        
        st.success(f"🔍 Mostrando {len(df_mostrar)} productos encontrados")
        
        # --- PREPARAR COLUMNAS Y ENCABEZADOS ---
        mapa_columnas = {
            'producto': 'Producto',
            'descripcion': 'Descripción',
            'temporada': 'Temporada',
            'stock': 'Stock',
            'nuevo precio': 'Precio'
        }
        
        # 1. Filtramos y renombramos
        cols_finales = [c for c in mapa_columnas.keys() if c in df_mostrar.columns]
        df_vista = df_mostrar[cols_finales].rename(columns=mapa_columnas)

        # 2. Limpieza de datos a numérico real para ordenar y formatear
        df_vista['Stock'] = pd.to_numeric(df_vista['Stock'], errors='coerce').fillna(0).astype(int)
        df_vista['Precio'] = pd.to_numeric(df_vista['Precio'], errors='coerce').fillna(0)

        # 3. ORDENAR: Por Stock de Mayor a Menor
        df_vista = df_vista.sort_values(by='Stock', ascending=False)

        # 4. Totalizar (lo guardamos para mostrarlo abajo y no romper el orden de la tabla)
        total_stock = df_vista['Stock'].sum()

        # 5. Aplicar formatos y colores condicionales (Rojo para negativos)
        def estilo_stock_negativo(val):
            color = '#D32F2F' if val < 0 else 'black'
            return f'color: {color}; font-weight: {"900" if val < 0 else "normal"}'

        # AQUÍ ESTÁ EL CAMBIO: usamos .map en lugar de .applymap
        df_estilado = df_vista.style.format({
            'Precio': lambda x: f"${int(x):,}".replace(",", ".") if x > 0 else "",
            'Stock': "{:d}"
        }).map(estilo_stock_negativo, subset=['Stock'])

        # 6. Forzar el color ROJO en los encabezados usando CSS
        st.markdown("""
            <style>
            [data-testid="stDataFrame"] th {
                background-color: #D32F2F !important;
                color: #FFFFFF !important;
                font-weight: 900 !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        # 7. Renderizar tabla
        st.dataframe(
            df_estilado,
            use_container_width=True,
            hide_index=True,
            height=450
        )

        # 8. Mostrar el TOTAL de forma destacada al pie de la tabla
        st.markdown(f"""
            <div style="background-color: #FEE2E2; padding: 10px; border-radius: 10px; text-align: center; border: 2px solid #D32F2F; margin-top: -10px;">
                <span style="color: #D32F2F; font-weight: 900; font-size: 18px;">TOTAL STOCK FILTRADO: {total_stock}</span>
            </div>
        """, unsafe_allow_html=True)
        
    else:
        st.error("No se pudo cargar la base de datos.")

# =======================================================
# --- VISTA 2: EL ESCÁNER ORIGINAL (Se oculta si estás en el listado) ---
# =======================================================
elif st.session_state.vista_actual == "escaner":

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

# --- PANTALLA DE RESULTADO ---
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

    # --- 2.5 NUEVO BLOQUE DE STOCK ---
    # Asumimos que la columna en tu Excel se llama 'stock' (se convierte a minúscula por la limpieza inicial)
    try:
        stock_disp = int(float(p.get('stock', 0))) # Convierte a entero por si viene con decimales
    except:
        stock_disp = 0
        
    # Colores dinámicos: Azul si hay stock, Rojo claro si es 0
    color_txt_stock = "#1E40AF" if stock_disp > 0 else "#B91C1C"
    color_bg_stock = "#DBEAFE" if stock_disp > 0 else "#FEE2E2"
    icono_stock = "📦" if stock_disp > 0 else "🚫"
    
    html_stock = f'<div style="margin-top: 10px; padding: 10px; background-color: {color_bg_stock}; color: {color_txt_stock}; border-radius: 8px; font-size: 25px; font-weight: 900;">{icono_stock} STOCK DISPONIBLE: {stock_disp}</div>'

    # 3. RESCATE DE CÓDIGO 9 DÍGITOS
    codigo_9 = st.session_state.get('codigo_completo', p.get('producto', ''))

    # 4. HTML EN UNA SOLA LÍNEA (Agregamos {html_stock} justo después de {html_obs})
    tarjeta_html = f'<div class="product-card"><div class="product-title">{str(p.get("descripcion", "PRODUCTO")).upper()}</div><div style="font-size: 15px; color: #64748b; font-weight: 700; margin-bottom: 15px; text-transform: uppercase; letter-spacing: 0.5px;">{str(p.get("departamento", "SIN DEPTO"))} | {str(p.get("subcategoria", "SIN CATEGORIA"))}</div><div class="price-value">$ {p_nue:,.0f}</div><div class="trend-pill {cls}">{var}</div>{html_obs}{html_stock}<div style="margin-top:25px; color:#444; font-size:18px; font-weight: 900; letter-spacing: 3px;">{codigo_9}</div><div style="margin-top:5px; color:#999; font-size:12px;">SKU BASE: {sku}</div></div>'
    
    st.markdown(tarjeta_html.replace(',', '.'), unsafe_allow_html=True)

    if st.button("🔄 CONSULTAR OTRO PRODUCTO", use_container_width=True):
        st.session_state.estado = "esperando"
        st.rerun()