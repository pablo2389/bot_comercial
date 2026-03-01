import streamlit as st
import pandas as pd
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN ---
URL = "https://tplhempahchujivvtrwk.supabase.co"
KEY = "sb_secret_U0Yp6xia6pt04BhzwQjvCQ_Ipx7-Zt_"
supabase = create_client(URL, KEY)

st.set_page_config(page_title="Dashboard Faltantes", layout="wide")
st.title("📊 Panel de Control de Clientes")

# --- 2. CARGA DE DATOS ---
def cargar_datos():
    try:
        res = supabase.table("faltantes").select("*").execute()
        return pd.DataFrame(res.data)
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

df = cargar_datos()

# --- 3. VISUALIZACIÓN ---
if not df.empty:
    st.success("¡Conexión exitosa! Datos encontrados.")
    
    # Métricas principales
    st.metric("Total de artículos en lista", len(df))
    
    # Buscamos la columna del nombre del artículo (item o artículo)
    col_item = 'item' if 'item' in df.columns else ('artículo' if 'artículo' in df.columns else df.columns[2])
    # Buscamos la columna de la persona (telegram_id o id del telegrama)
    col_user = 'telegram_id' if 'telegram_id' in df.columns else df.columns[-1]

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📦 Stock de Faltantes")
        # Gráfico de barras por artículo
        st.bar_chart(df[col_item].value_counts())

    with col2:
        st.subheader("👤 Pedidos por Usuario")
        # Gráfico de barras por quién pidió
        st.bar_chart(df[col_user].value_counts())

    st.subheader("📝 Detalle de Registros")
    st.dataframe(df, use_container_width=True)

else:
    st.info("No hay datos nuevos. Cargá más filas en Supabase.")

if st.button('🔄 Actualizar Dashboard'):
    st.rerun()