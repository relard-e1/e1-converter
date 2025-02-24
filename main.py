from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware  # CORS-Import hinzufügen
from fastapi.responses import JSONResponse, FileResponse 
import pdfplumber
import pandas as pd
import re
import os
import time

app = FastAPI()

# CORS für alle Domains und Methoden aktivieren
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hier nur erlaubte Domains angeben, z. B. ["http://127.0.0.1:5500"]
    allow_credentials=True,
    allow_methods=["*"],  # Erlaubt GET, POST, DELETE usw.
    allow_headers=["*"],  # Erlaubt alle Header
)

UPLOAD_FOLDER = "uploads"
CSV_FOLDER = "csv"
BASE_URL = "https://e1-converter.onrender.com/download/"  # Deine URL für Downloads

os.makedirs(CSV_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.get("/")
async def root():
    return {"message": "PDF-zu-CSV API ist live!"}


@app.get("/download/{filename}")
async def download_csv(filename: str):
    file_path = os.path.join(CSV_FOLDER, filename)
    
    # Debugging: Überprüfen, ob die Datei existiert
    if not os.path.exists(file_path):
        print(f"🚨 Datei nicht gefunden: {file_path}")
        return {"error": f"File {filename} not found at {file_path}"}

    print(f"✅ CSV-Datei gefunden: {file_path}")
    return FileResponse(file_path, filename=filename, media_type="text/csv")


@app.post("/process-pdf/")
async def process_pdf(file: UploadFile = File(...)):
    # Erstelle einen eindeutigen Zeitstempel
    timestamp = int(time.time())

    #  Generiere einen neuen Dateinamen mit Zeitstempel
    original_filename = os.path.splitext(file.filename)[0]  # Entfernt ".PDF"
    new_filename = f"{original_filename}_{timestamp}.PDF".replace(" ", "_")  # Leerzeichen ersetzen
    file_path = os.path.join(UPLOAD_FOLDER, new_filename)

    # Datei speichern
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # Prüfen, ob die Datei wirklich eine PDF ist
    with open(file_path, "rb") as f:
        file_header = f.read(5)
        if not file_header.startswith(b"%PDF-"):
            return {"error": "Die Datei ist keine gültige PDF-Datei."}

    # PDF verarbeiten
    csv_path = extract_pdf_data(file_path, timestamp)

    #  Generiere die Download-URL
    download_url = f"{BASE_URL}{os.path.basename(csv_path)}"

    return JSONResponse(content={"csv_url": download_url})


def extract_pdf_data(pdf_path, timestamp):
    data = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_lines = page.extract_text().split("\n")
            data.extend(parse_order_lines(text_lines))

    df = pd.DataFrame(data, columns=["sku", "qty", "uom_left", "qty-2", "uom_right", "name"])

    # Dateiname mit Zeitstempel
    original_filename = os.path.splitext(os.path.basename(pdf_path))[0]  # Entfernt ".PDF"
    csv_filename = f"{original_filename}_{timestamp}.csv"
    csv_path = os.path.join(CSV_FOLDER, csv_filename)
    
    df.to_csv(csv_path, index=False, sep=";")
    
    print(f"✅ CSV gespeichert unter: {csv_path}")
    return csv_path

def parse_order_lines(text_lines):
    order_lines = []

    print("\n🔎 Suche nach Bestellungen...")
    i = 0
    while i < len(text_lines) - 2:  # Mindestens 3 Zeilen müssen noch da sein
        line = text_lines[i]

        # Fall 1: SKU ist vorhanden
        sku_match = re.search(r"(\d{4,}-\d{6,}-\d{3}) /(\d+)", line)
        if sku_match:
            sku = sku_match.group(1).strip()  # SKU
            name = text_lines[i + 1].strip()  # Produktname steht in der nächsten Zeile
            print(f"🔹 Gefunden: SKU={sku}, Produktname={name}")

            # Mengenangaben und Einheiten in den nächsten Zeilen suchen
            qty = None
            uom_left = None
            qty_2 = None
            uom_right = None

            for j in range(2, 6):
                if i + j < len(text_lines):
                    # Mengenzeile aufteilen
                    parts = text_lines[i + j].split()
                    if "*" in parts:  # Sicherstellen, dass das * Zeichen vorhanden ist
                        try:
                            idx_star = parts.index("*")  # Index des "*" Zeichens
                            qty = int(parts[idx_star - 2])  # Erste Mengenangabe (qty)
                            uom_left = parts[idx_star - 1]  # Erste Einheit (uom_left)

                            # ✅ Fix für `qty-2`: Tausendertrennzeichen entfernen
                            raw_qty_2 = parts[idx_star + 2].replace(",", "")  # Entfernt `,`
                            qty_2 = int(raw_qty_2) if raw_qty_2.isdigit() else float(raw_qty_2)

                            uom_right = parts[idx_star + 3]  # Zweite Einheit (uom_right)

                            print(f"   ➡ Menge gefunden: {qty} {uom_left}, {qty_2} {uom_right}")
                            break  # Falls gefunden, abbrechen
                        except (IndexError, ValueError):
                            print(f"⚠️ Fehler beim Parsen der Mengenangaben für SKU {sku}")

            # Falls eine Variable nicht gefunden wurde, setzen wir Standardwerte
            sku = sku if sku else "N/A"
            qty = qty if qty is not None else 0
            uom_left = uom_left if uom_left else "N/A"
            qty_2 = qty_2 if qty_2 is not None else 0
            uom_right = uom_right if uom_right else "N/A"
            name = name if name else "N/A"

            # Falls alle Werte vorhanden sind, speichern
            order_lines.append([sku, qty, uom_left, qty_2, uom_right, name])
            i += 4  # Überspringe 4 Zeilen (SKU, Name, Zusatzinfo, Mengenzeile)
        
        elif re.match(r"^\d+\s+/", line):  # Bestellposition beginnt mit einer Zahl und "/"
            print(f"🔸 Alternative Extraktion: Zeile {i} erkannt als Bestellposition.")

            # Produktname aus der nächsten Zeile
            name = text_lines[i + 1].strip() if i + 1 < len(text_lines) else "N/A"

            # Mengenangaben aus der dritten Zeile
            qty = None
            uom_left = None
            qty_2 = None
            uom_right = None

            if i + 2 < len(text_lines):
                parts = text_lines[i + 2].split()
                if "X" in parts:
                    try:
                        idx_x = parts.index("X")  # Index von "X"
                        qty = int(parts[idx_x - 1])  # Erste Menge (qty-1)
                        uom_left = parts[idx_x + 1]  # Erste Einheit (uom_left)
                        # Falls noch weitere Werte folgen:
                        if idx_x + 3 < len(parts):
                            raw_qty_2 = parts[idx_x + 2].replace(",", "")
                            qty_2 = int(raw_qty_2) if raw_qty_2.isdigit() else float(raw_qty_2)
                            uom_right = parts[idx_x + 3]
                        else:
                            qty_2 = 0
                            uom_right = "N/A"

                        print(f"   ➡ Menge gefunden: {qty} {uom_left}, {qty_2} {uom_right}")
                    except (IndexError, ValueError):
                        print(f"⚠️ Fehler beim Parsen der Mengenangaben für Produkt {name}")

            # Falls eine Variable nicht gefunden wurde, setzen wir Standardwerte
            sku = "N/A"
            qty = qty if qty is not None else 0
            uom_left = uom_left if uom_left else "N/A"
            qty_2 = qty_2 if qty_2 is not None else 0
            uom_right = uom_right if uom_right else "N/A"
            name = name if name else "N/A"

            order_lines.append([sku, qty, uom_left, qty_2, uom_right, name])
            i += 3  # Überspringe 3 Zeilen (Bestellnummer, Name, Mengenzeile)

        else:
            i += 1  # Falls die Zeile keine Bestellposition ist, zur nächsten springen

    return order_lines
