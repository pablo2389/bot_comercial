import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

# 1. CARGA DE CONFIGURACIÓN
load_dotenv()

# Usamos variables de entorno para que GitHub no bloquee el push
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configuración de la página
st.set_page_config(page_title="Dashboard Faltantes", layout="wide", page_icon="📊")
st.title("📊 Panel de Control de Faltantes")

# --- 2. FUNCIÓN DE CARGA DE DATOS ---
def cargar_datos():
    try:
        # Traemos todo de la tabla 'faltantes'
        res = supabase.table("faltantes").select("*").execute()
        if res.data:
            return pd.DataFrame(res.data)
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return pd.DataFrame()

df = cargar_datos()

# --- 3. VISUALIZACIÓN ---
if not df.empty:
    st.success("✅ Conexión exitosa con Supabase.")
    
    # Métricas principales
    st.metric("Artículos faltantes", len(df))
    
    # Identificamos las columnas correctas basándonos en tu captura de Supabase
    # Columna del artículo: 'producto'
    # Columna del usuario: 'telegram_id'
    col_item = 'producto' if 'producto' in df.columns else df.columns[0]
    col_user = 'telegram_id' if 'telegram_id' in df.columns else df.columns[-1]

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📦 Stock de Faltantes")
        # Gráfico de barras por producto
        conteo_productos = df[col_item].value_counts()
        st.bar_chart(conteo_productos)

    with col2:
        st.subheader("👤 Pedidos por Usuario")
        # Gráfico de barras por quién anotó
        conteo_usuarios = df[col_user].value_counts()
        st.bar_chart(conteo_usuarios)

    st.subheader("📝 Detalle de Registros")
    # Mostramos la tabla completa ordenada por lo más nuevo
    if 'created_at' in df.columns:
        df = df.sort_values(by='created_at', ascending=False)
    
    st.dataframe(df, use_container_width=True)

else:
    st.info("Aún no hay faltantes registrados. ¡Anotá algo desde el Bot!")

# Botón de actualización manual
if st.button('🔄 Actualizar Datos'):
    st.rerun()