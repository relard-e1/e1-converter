from fastapi import FastAPI, File, UploadFile
import pdfplumber
import pandas as pd
import re
import os

app = FastAPI()

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.post("/process-pdf/")
async def process_pdf(file: UploadFile = File(...)):
    # Datei speichern
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # PDF verarbeiten
    csv_path = extract_pdf_data(file_path)
    
    return {"csv_url": f"https://deinserver.com/download/{os.path.basename(csv_path)}"}

def extract_pdf_data(pdf_path):
    data = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_lines = page.extract_text().split("\n")
            data.extend(parse_order_lines(text_lines))

    df = pd.DataFrame(data, columns=["SKU", "Produktname", "Menge"])
    csv_path = pdf_path.replace(".PDF", ".csv")
    df.to_csv(csv_path, index=False, sep=";")
    
    return csv_path

def parse_order_lines(text_lines):
    order_lines = []
    for i in range(len(text_lines) - 5):
        line = text_lines[i]
        sku_match = re.search(r"(\d{4,}-\d{6,}-\d{3}) /(\d{11,})", line)
        if sku_match:
            current_sku = sku_match.group(1).strip()
            current_product = text_lines[i + 1].strip()
            for j in range(2, 6):
                if i + j < len(text_lines):
                    qty_match = re.search(r"(\d+) ST", text_lines[i + j])
                    if qty_match:
                        current_qty = int(qty_match.group(1))
                        break
            if current_sku and current_product and current_qty:
                order_lines.append([current_sku, current_product, current_qty])
    return order_lines  
