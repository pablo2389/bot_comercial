import os
import re
import urllib.parse
from datetime import datetime, date
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
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Diccionario global para manejar los carritos de los usuarios
carritos = {}

def obtener_teclado():
    return ReplyKeyboardMarkup([
        ['🛒 Carrito Nuevo', '🧾 Finalizar Ticket'],
        ['❌ Borrar Último', '🗑️ Vaciar Carrito'],
        ['📊 Caja del Día', '📄 Reporte PDF'],
        ['🔄 Reiniciar Menú']
    ], resize_keyboard=True)

# --- 2. LÓGICA DEL PDF ---
def generar_pdf_ventas(ventas):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"reporte_{timestamp}.pdf"
    temp_dir = os.path.join(os.getcwd(), "pdf_temp")
    os.makedirs(temp_dir, exist_ok=True)
    
    filepath = os.path.join(temp_dir, filename)
    c = canvas.Canvas(filepath, pagesize=letter)
    width, height = letter
    y = height - 50

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, f"Reporte Almacén - {datetime.now().strftime('%d/%m/%Y')}")
    y -= 40

    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Producto")
    c.drawString(200, y, "Monto")
    c.drawString(350, y, "Cliente")
    c.drawString(450, y, "Tipo")
    y -= 20
    c.line(50, y+15, 550, y+15)

    c.setFont("Helvetica", 10)
    for v in ventas:
        if y < 60:
            c.showPage()
            y = height - 50
        prod = str(v.get("producto") or "Varios")
        monto = v.get("precio") or 0
        cli_raw = v.get("cliente")
        cli = (str(cli_raw) or "Anónimo").capitalize()
        tipo = str(v.get("tipo") or "venta")
        c.drawString(50, y, prod[:25])
        c.drawString(200, y, f"${monto}")
        c.drawString(350, y, cli)
        c.drawString(450, y, tipo)
        y -= 15
    c.save()
    return filepath

# --- 3. MANEJADORES DE COMANDOS Y MENSAJES ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 **SISTEMA DE VENTAS ACTIVO**", reply_markup=obtener_teclado(), parse_mode='Markdown')

async def enviar_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user.id
    await update.message.reply_text("⏳ Generando reporte de hoy...")
    hoy = date.today().isoformat()
    # Cambiado a 'id_telegrama'
    res = supabase.table("ventas").select("*").eq("id_telegrama", str(u)).gte("fecha", hoy).execute()
    if not res.data:
        await update.message.reply_text("❌ No hay ventas registradas hoy.")
        return
    path_pdf = generar_pdf_ventas(res.data)
    with open(path_pdf, 'rb') as f:
        await update.message.reply_document(document=f, filename=os.path.basename(path_pdf))
    os.remove(path_pdf)

async def procesar_entrada_carrito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in carritos: 
        return
    
    partes = re.split(r'[,\.\n]', update.message.text)
    for parte in partes:
        pedazo = parte.strip()
        if not pedazo: continue
        num = re.findall(r'\d+', pedazo)
        pal = re.findall(r'[a-zA-ZáéíóúÁÉÍÓÚñÑ]+', pedazo)
        if not num: continue
        
        cant, precio = (int(num[0]), int(num[-1])) if len(num) >= 2 else (1, int(num[0]))
        carritos[user_id].append({
            "producto": " ".join(pal) or "Prod", 
            "cantidad": cant, 
            "precio": precio, 
            "subtotal": cant * precio
        })
    
    resumen = "📝 **CARRITO:**\n" + "\n".join([f"• {i['cantidad']}x {i['producto']} — ${i['subtotal']}" for i in carritos[user_id]])
    await update.message.reply_text(f"{resumen}\n\n💰 **TOTAL: ${sum(i['subtotal'] for i in carritos[user_id])}**", parse_mode='Markdown')

async def finalizar_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user.id
    
    if u not in carritos or not carritos[u]:
        await update.message.reply_text("⚠️ El carrito está vacío.")
        return

    cliente = " ".join(context.args).lower() if (context.args and len(context.args) > 0) else "cliente"
    total = sum(i['subtotal'] for i in carritos[u])
    
    txt_ws = f"🧾 *TICKET: {cliente.upper()}*\n"
    for i in carritos[u]:
        txt_ws += f"• {i['cantidad']}x {i['producto']}: ${i['subtotal']}\n"
        # Cambiado a 'id_telegrama'
        supabase.table("ventas").insert({
            "producto": f"{i['cantidad']}x {i['producto']}", 
            "precio": i['subtotal'], 
            "cliente": cliente, 
            "tipo": "venta", 
            "id_telegrama": str(u), 
            "fecha": datetime.now().isoformat()
        }).execute()
    
    txt_ws += f"\n💰 *TOTAL: ${total}*"
    url_ws = f"https://wa.me/?text={urllib.parse.quote(txt_ws)}"
    
    kb = [
        [InlineKeyboardButton("💵 Efectivo", callback_data=f"p_efe_{cliente}_{total}"), 
         InlineKeyboardButton("📱 Transf.", callback_data=f"p_tra_{cliente}_{total}")],
        [InlineKeyboardButton("⏳ Fiado", callback_data=f"p_fia_{cliente}_{total}")],
        [InlineKeyboardButton("📲 ENVIAR TICKET (WhatsApp)", url=url_ws)]
    ]
    
    await update.message.reply_text(f"🧾 **TOTAL: ${total}**\n¿Cómo pagó?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
    carritos[u] = []

async def manejador_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    markup = q.message.reply_markup
    d = q.data.split("_")
    
    if d[0] == "p":
        t, c, m = d[1], d[2], int(d[3])
        tipo = "EFECTIVO" if t == 'efe' else "TRANSFERENCIA" if t == 'tra' else "FIADO"
        
        if t != 'fia':
            # Cambiado a 'id_telegrama'
            supabase.table("ventas").insert({
                "producto": f"PAGO {tipo}", 
                "precio": m, 
                "cliente": c, 
                "tipo": "pago", 
                "id_telegrama": str(q.from_user.id), 
                "fecha": datetime.now().isoformat()
            }).execute()
            
        await q.edit_message_text(f"✅ **REGISTRADO: {c.upper()}**\n💰 ${m} ({tipo})\n\nPodés seguir enviando el ticket:", reply_markup=markup, parse_mode='Markdown')

async def gestionar_mensajes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t, u = update.message.text, update.effective_user.id
    
    if t == '🛒 Carrito Nuevo': 
        carritos[u] = [] 
        await update.message.reply_text("🛒 **CARRITO ABIERTO**", parse_mode='Markdown')
    
    elif t == '🧾 Finalizar Ticket':
        await finalizar_ticket(update, context)

    elif t == '❌ Borrar Último':
        if u in carritos and carritos[u]:
            carritos[u].pop()
            await update.message.reply_text("🗑️ Último producto eliminado.")
        else:
            await update.message.reply_text("El carrito ya está vacío.")

    elif t == '🗑️ Vaciar Carrito':
        carritos[u] = []
        await update.message.reply_text("🧹 Carrito vaciado por completo.")

    elif t == '📄 Reporte PDF': 
        await enviar_pdf(update, context)
        
    elif t == '📊 Caja del Día':
        # Cambiado a 'id_telegrama'
        res = supabase.table("ventas").select("*").eq("id_telegrama", str(u)).gte("fecha", date.today().isoformat()).execute()
        v = sum(r['precio'] for r in res.data if r['tipo'] == 'venta')
        p = sum(r['precio'] for r in res.data if r['tipo'] == 'pago')
        await update.message.reply_text(f"📊 **HOY**\n💰 Ventas: ${v}\n💵 Cobrado: ${p}", parse_mode='Markdown')
        
    elif t == '🔄 Reiniciar Menú': 
        await start(update, context)
        
    elif u in carritos: 
        await procesar_entrada_carrito(update, context)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ticket", finalizar_ticket))
    app.add_handler(CommandHandler("pdf", enviar_pdf))
    app.add_handler(CallbackQueryHandler(manejador_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gestionar_mensajes))
    
    print("Bot en marcha (id_telegrama corregido)...")# Mensajes de texto y botones del teclado
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gestionar_mensajes))
    
    print("Bot en marcha (id_telegrama corregido)...")
    app.run_polling()