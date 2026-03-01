from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime
import os

def generar_pdf_ventas(ventas, filename=None):
    if filename is None:
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
    saldos = {}

    for v in ventas:
        if y < 60:
            c.showPage()
            y = height - 50
        
        prod = str(v.get("producto") or "Varios")
        monto = v.get("precio") or 0
        cli_raw = v.get("cliente")
        cli = str(cli_raw).capitalize() if cli_raw else "Anónimo"
        tipo = str(v.get("tipo") or "venta")

        c.drawString(50, y, prod)
        c.drawString(200, y, f"${monto}")
        c.drawString(350, y, cli)
        c.drawString(450, y, tipo)
        
        if cli not in saldos: saldos[cli] = 0
        if tipo == "venta": saldos[cli] += monto
        else: saldos[cli] -= monto
        y -= 15

    c.save()
    return filepath