from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse
import pdfplumber
import pandas as pd
import re
import os

app = FastAPI()

UPLOAD_FOLDER = "uploads"
CSV_FOLDER = "csv"
os.makedirs(CSV_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.get("/")
async def root():
    return {"message": "PDF-zu-CSV API ist live!"}

@app.get("/download/{filename}")
async def download_csv(filename: str):
    file_path = os.path.join(CSV_FOLDER, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename, media_type="text/csv")
    return {"error": "File not found"}

@app.post("/process-pdf/")
async def process_pdf(file: UploadFile = File(...)):
    # Datei speichern
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # 🔹 Debug: Prüfen, ob die Datei wirklich empfangen wurde
    if os.path.exists(file_path):
        print(f"📂 Datei erhalten: {file.filename}, Größe: {os.path.getsize(file_path)} Bytes")
    else:
        print("🚨 Datei wurde NICHT gespeichert!")

    # Debug: Falls die Datei leer ist, Fehler zurückgeben
    if os.path.getsize(file_path) == 0:
        return {"error": "Die Datei ist leer oder konnte nicht korrekt gespeichert werden."}

    # Prüfen, ob die Datei eine echte PDF ist
    with open(file_path, "rb") as f:
        file_header = f.read(5)
        if not file_header.startswith(b"%PDF-"):
            return {"error": "Die Datei ist keine gültige PDF-Datei."}

    # PDF verarbeiten
    csv_path = extract_pdf_data(file_path)

    return {"csv_url": f"https://dein-projekt.onrender.com/download/{os.path.basename(csv_path)}"}


def extract_pdf_data(pdf_path):
    data = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_lines = page.extract_text().split("\n")
            data.extend(parse_order_lines(text_lines))

    df = pd.DataFrame(data, columns=["SKU", "Produktname", "Menge"])
    
    # Speichere CSV direkt im gleichen Ordner wie die PDFs, falls notwendig
    csv_filename = os.path.basename(pdf_path).replace(".PDF", ".csv")
    csv_path = os.path.join(CSV_FOLDER, csv_filename)
    
    df.to_csv(csv_path, index=False, sep=";")
    
    print(f"✅ CSV gespeichert unter: {csv_path}")
    return csv_path

def parse_order_lines(text_lines):
    order_lines = []
    current_sku = None
    current_product = None
    current_qty = None

    print("\n🔎 Suche nach Bestellungen...")
    for i in range(len(text_lines) - 5):  # Puffer für QTY-Suche
        line = text_lines[i]

        # Neue Regex für SKU – jetzt erkennt sie auch Positionsnummern davor
        sku_match = re.search(r"(\d{4,}-\d{6,}-\d{3}) /(\d{11,})", line)
        if sku_match:
            current_sku = sku_match.group(1).strip()  # SKU
            current_product = text_lines[i + 1].strip()  # Produktname steht in der nächsten Zeile
            print(f"🔹 Gefunden: SKU={current_sku}, Produktname={current_product}")

            # Mengenangabe in den nächsten 5 Zeilen suchen
            for j in range(2, 6):
                if i + j < len(text_lines):
                    qty_match = re.search(r"(\d+) ST", text_lines[i + j])
                    if qty_match:
                        current_qty = int(qty_match.group(1))
                        print(f"   ➡ Menge gefunden: {current_qty} ST")
                        break  # Falls gefunden, abbrechen

            # Falls alle Werte vorhanden sind, speichern
            if current_sku and current_product and current_qty:
                order_lines.append([current_sku, current_product, current_qty])

                # Zurücksetzen für die nächste Bestellung
                current_sku = None
                current_product = None
                current_qty = None

    return order_lines
