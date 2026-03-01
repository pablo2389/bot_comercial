import os
import re
import time
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from supabase import create_client, Client
from dotenv import load_dotenv

# Librerías para el PDF
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# --- 1. CONFIGURACIÓN INICIAL ---
load_dotenv()
TOKEN = os.getenv("TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Conexión a Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Diccionarios de estado
carritos = {}
esperando_nombre = {}
esperando_pago_deuda = {}

def obtener_teclado():
    return ReplyKeyboardMarkup([
        ['🛒 Carrito Nuevo', '🧾 Finalizar Ticket'],
        ['❌ Borrar Último', '🗑️ Vaciar Carrito'],
        ['📊 Caja del Día', '📄 Reporte PDF'],
        ['📉 Lista Deudores', '🔄 Reiniciar Menú']
    ], resize_keyboard=True)

# --- 2. LÓGICA DE PDF ---

def generar_ticket_pdf(cliente, ventas_actuales):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ticket_{cliente}_{timestamp}.pdf"
    temp_dir = os.path.join(os.getcwd(), "pdf_temp")
    os.makedirs(temp_dir, exist_ok=True)
    filepath = os.path.join(temp_dir, filename)
    
    c = canvas.Canvas(filepath, pagesize=letter)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, 750, f"TICKET: {cliente.upper()}")
    c.setFont("Helvetica", 10)
    c.drawString(50, 730, f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    
    y = 700
    total = 0
    for i in ventas_actuales:
        c.drawString(50, y, f"{i['cantidad']}x {i['producto']}")
        c.drawString(400, y, f"${i['subtotal']}")
        total += i['subtotal']
        y -= 20
        
    c.line(50, y, 550, y)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y-25, f"TOTAL: ${total}")
    c.save()
    return filepath

def generar_reporte_periodo(registros, titulo):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reporte_{titulo.lower()}_{timestamp}.pdf"
    temp_dir = os.path.join(os.getcwd(), "pdf_temp")
    os.makedirs(temp_dir, exist_ok=True)
    filepath = os.path.join(temp_dir, filename)
    
    c = canvas.Canvas(filepath, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 750, f"REPORTE DE VENTAS: {titulo.upper()}")
    
    y = 700
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Fecha")
    c.drawString(130, y, "Cliente")
    c.drawString(250, y, "Concepto")
    c.drawString(480, y, "Monto")
    y -= 15
    c.line(50, y, 550, y)
    y -= 20
    
    c.setFont("Helvetica", 9)
    total_v, total_p = 0, 0
    for r in registros:
        if y < 50:
            c.showPage()
            y = 750
        fecha = datetime.fromisoformat(r['fecha']).strftime('%d/%m %H:%M')
        c.drawString(50, y, fecha)
        c.drawString(130, y, str(r['cliente'])[:15])
        c.drawString(250, y, str(r['producto'])[:35])
        monto = r['precio']
        if r['tipo'] == 'venta':
            c.drawString(480, y, f"+ ${monto}")
            total_v += monto
        else:
            c.drawString(480, y, f"- ${monto}")
            total_p += monto
        y -= 15
        
    y -= 25
    c.line(50, y+20, 550, y+20)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, f"VENTAS: ${total_v} | COBRADO: ${total_p} | PENDIENTE: ${total_v - total_p}")
    c.save()
    return filepath

# --- 3. MANEJADORES ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 **SISTEMA DE GESTIÓN ACTIVO**", reply_markup=obtener_teclado(), parse_mode='Markdown')

async def mostrar_caja_del_dia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = str(update.effective_user.id)
    hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    res = supabase.table("ventas").select("*").eq("id_telegrama", u).gte("fecha", hoy).execute()
    v = sum(r['precio'] for r in res.data if r['tipo'] == 'venta')
    p = sum(r['precio'] for r in res.data if r['tipo'] == 'pago')
    txt = f"📊 **BALANCE DE HOY**\n💰 Ventas: ${v}\n💵 Entró a caja: ${p}\n📉 Fiado: ${v-p}"
    await update.message.reply_text(txt, parse_mode='Markdown')

async def ver_deudores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = str(update.effective_user.id)
    res = supabase.table("ventas").select("*").eq("id_telegrama", u).execute()
    saldos = {}
    for r in res.data:
        cli = r['cliente'].strip().capitalize()
        saldos[cli] = saldos.get(cli, 0) + (r['precio'] if r['tipo'] == 'venta' else -r['precio'])
    
    kb = []
    txt = "📉 **DEUDORES ACTUALES:**\n"
    for c, t in saldos.items():
        if t > 0:
            txt += f"• {c}: debe **${t}**\n"
            kb.append([InlineKeyboardButton(f"✅ Cobrar a {c}", callback_data=f"cobrar_{c}_{t}")])
    
    if not kb:
        await update.message.reply_text("✅ No hay deudas.")
    else:
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def manejador_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data.split("_")
    u = str(q.from_user.id)

    if d[0] == "p":
        t, c, m = d[1], d[2], d[3]
        if t != 'fia':
            supabase.table("ventas").insert({
                "producto": f"PAGO {t.upper()}", "precio": int(m), 
                "cliente": c.lower(), "tipo": "pago", "id_telegrama": u, 
                "fecha": datetime.now().isoformat()
            }).execute()
            txt = f"✅ **PAGADO: {c.upper()}** (${m})"
        else:
            txt = f"⏳ **FIADO: {c.upper()}** (${m})"
        
        await q.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📄 Descargar Ticket", callback_data=f"gentick_{c}")]]), parse_mode='Markdown')

    elif d[0] == "cobrar":
        esperando_pago_deuda[int(u)] = {'cliente': d[1], 'deuda': d[2]}
        await q.message.reply_text(f"💰 {d[1]} debe ${d[2]}.\n¿Cuánto paga?")
        await q.answer()

    elif d[0] == "gentick":
        datos = context.user_data.get('ultimo_ticket')
        if datos:
            path = generar_ticket_pdf(datos['cliente'], datos['productos'])
            with open(path, 'rb') as f:
                await q.message.reply_document(document=f)
            os.remove(path)
        await q.answer()

    elif d[0] == "rep":
        tipo = d[1]
        ahora = datetime.now()
        if tipo == "hoy": inicio = ahora.replace(hour=0, minute=0, second=0).isoformat()
        elif tipo == "semana": inicio = (ahora - timedelta(days=ahora.weekday())).replace(hour=0, minute=0, second=0).isoformat()
        elif tipo == "mes": inicio = ahora.replace(day=1, hour=0, minute=0, second=0).isoformat()
        else: inicio = ahora.replace(month=1, day=1, hour=0, minute=0, second=0).isoformat()
        
        await q.answer("Generando reporte...")
        res = supabase.table("ventas").select("*").eq("id_telegrama", u).gte("fecha", inicio).order("fecha").execute()
        if res.data:
            path = generar_reporte_periodo(res.data, tipo)
            with open(path, 'rb') as f:
                await q.message.reply_document(document=f, caption=f"Reporte {tipo} generado con éxito.")
            os.remove(path)
        else:
            await q.message.reply_text("No hay datos para este periodo.")

async def gestionar_mensajes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t, u = update.message.text, update.effective_user.id

    if u in esperando_pago_deuda:
        try:
            m = int(t.strip())
            c = esperando_pago_deuda[u]['cliente']
            supabase.table("ventas").insert({"producto": "ABONO DEUDA", "precio": m, "cliente": c.lower(), "tipo": "pago", "id_telegrama": str(u), "fecha": datetime.now().isoformat()}).execute()
            esperando_pago_deuda.pop(u)
            await update.message.reply_text(f"✅ Cobrado ${m} a {c}.", reply_markup=obtener_teclado())
        except:
            await update.message.reply_text("Enviá solo números.")
        return

    if u in esperando_nombre:
        c = t.strip()
        esperando_nombre.pop(u)
        tot = sum(i['subtotal'] for i in carritos[u])
        context.user_data['ultimo_ticket'] = {'cliente': c, 'productos': list(carritos[u]), 'total': tot}
        
        for i in carritos[u]:
            supabase.table("ventas").insert({
                "producto": f"{i['cantidad']}x {i['producto']}", 
                "precio": i['subtotal'], "cliente": c.lower(), 
                "tipo": "venta", "id_telegrama": str(u), 
                "fecha": datetime.now().isoformat()
            }).execute()
            
        kb = [[InlineKeyboardButton("💵 Efectivo", callback_data=f"p_efe_{c}_{tot}"), InlineKeyboardButton("📱 Transf.", callback_data=f"p_tra_{c}_{tot}")],
              [InlineKeyboardButton("⏳ Fiado", callback_data=f"p_fia_{c}_{tot}")]]
        await update.message.reply_text(f"🧾 Ticket {c}: ${tot}", reply_markup=InlineKeyboardMarkup(kb))
        carritos[u] = []
        return

    if t == '🛒 Carrito Nuevo':
        carritos[u] = []
        await update.message.reply_text("🛒 Carrito abierto. Enviame productos (ej: 2 pan 500)")
    elif t == '🧾 Finalizar Ticket':
        if u in carritos and carritos[u]:
            esperando_nombre[u] = True
            await update.message.reply_text("👤 ¿Nombre del cliente?")
        else:
            await update.message.reply_text("El carrito está vacío.")
    elif t == '📉 Lista Deudores':
        await ver_deudores(update, context)
    elif t == '📊 Caja del Día':
        await mostrar_caja_del_dia(update, context)
    elif t == '📄 Reporte PDF': 
        kb = [[InlineKeyboardButton("📅 Hoy", callback_data="rep_hoy"), InlineKeyboardButton("🗓️ Semana", callback_data="rep_semana")],
              [InlineKeyboardButton("📆 Mes", callback_data="rep_mes"), InlineKeyboardButton("🚀 Año", callback_data="rep_año")]]
        await update.message.reply_text("📄 **¿Qué reporte PDF necesitas?**", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    elif t == '🔄 Reiniciar Menú':
        await start(update, context)
    elif u in carritos:
        n = re.findall(r'\d+', t)
        p = re.findall(r'[a-zA-ZñÑáéíóúÁÉÍÓÚ]+', t)
        if n:
            can, pre = (int(n[0]), int(n[-1])) if len(n) >= 2 else (1, int(n[0]))
            prod_nom = " ".join(p) if p else "Producto"
            carritos[u].append({"producto": prod_nom, "cantidad": can, "precio": pre, "subtotal": can * pre})
            await update.message.reply_text(f"✅ {prod_nom} agregado. Subtotal: ${can * pre}\nTotal actual: ${sum(i['subtotal'] for i in carritos[u])}")

if __name__ == '__main__':
    # Configuración de la aplicación con timeouts extendidos
    app = ApplicationBuilder().token(TOKEN).connect_timeout(60).read_timeout(60).write_timeout(60).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("inicio", start))
    app.add_handler(CallbackQueryHandler(manejador_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gestionar_mensajes))
    
    print("--- INICIANDO SISTEMA ---")
    
    # Bucle infinito para evitar caídas por error DNS en Hugging Face
    while True:
        try:
            print("Intentando conectar con Telegram...")
            app.run_polling(drop_pending_updates=True)
        except Exception as e:
            print(f"Error detectado: {e}")
            print("Reiniciando conexión en 5 segundos...")
            time.sleep(5)