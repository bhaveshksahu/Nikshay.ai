import io
from PIL import Image
import os
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
import google.generativeai as genai
from datetime import date, timedelta
import base64, json, random

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Make sure your .env file has GEMINI_API_KEY=your_key_here
genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))

# ── In-memory data ──────────────────────
PATIENTS = {
    "P001": {"name": "Ravi Kumar", "village": "Harda", "phone": "9876543210"},
    "P002": {"name": "Sunita Devi", "village": "Harda", "phone": "9876543211"},
    "P003": {"name": "Arjun Sharma", "village": "Betul", "phone": "9876543212"},
    "P004": {"name": "Meera Bai", "village": "Khandwa", "phone": "9876543213"},
    "P005": {"name": "Suresh Yadav", "village": "Harda", "phone": "9876543214"},
    "P006": {"name": "Kavita Singh", "village": "Betul", "phone": "9876543215"},
}

random.seed(42)
DOSES = {}
for pid in PATIENTS:
    DOSES[pid] = {}
    for i in range(7):
        d = (date.today() - timedelta(days=i)).isoformat()
        if pid == "P001":
            DOSES[pid][d] = i >= 4
        elif pid == "P002":
            DOSES[pid][d] = i >= 2
        else:
            DOSES[pid][d] = random.random() > 0.1

def get_risk(pid):
    records = DOSES.get(pid, {})
    recent = sorted(records.items(), reverse=True)[:7]
    missed = sum(1 for _, confirmed in recent if not confirmed)
    if missed >= 4: return "red"
    if missed >= 2: return "amber"
    return "green"

def get_all_patients():
    result = []
    for pid, info in PATIENTS.items():
        p = dict(info)
        p["id"] = pid
        p["risk"] = get_risk(pid)
        p["doses"] = DOSES.get(pid, {})
        missed = sum(1 for v in list(DOSES.get(pid,{}).values())[:7] if not v)
        p["missed_7days"] = missed
        result.append(p)
    result.sort(key=lambda x: {"red":0,"amber":1,"green":2}[x["risk"]])
    return result

def verify_pill(image_bytes: bytes) -> dict:
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        img = {"mime_type": "image/jpeg",
               "data": base64.b64encode(image_bytes).decode()}
        prompt = """Look at this photo. Is a tablet or pill clearly visible?
Reply ONLY with valid JSON, no markdown:
{"pill_visible": true, "confidence": 0.95, "notes": "pill seen in palm"}"""
        resp = model.generate_content([img, prompt])
        text = resp.text.strip().replace("```json","").replace("```","").strip()
        return json.loads(text)
    except Exception as e:
        return {"pill_visible": False, "confidence": 0.0, "notes": str(e)}

def generate_sms(name: str, missed: int) -> str:
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"""Write a caring, short SMS in Hindi for TB patient {name}
who missed {missed} doses. Max 2 sentences. Warm tone. ONLY the message."""
        resp = model.generate_content(prompt)
        return resp.text.strip()
    except Exception as e:
        print(f"SMS Error: {e}")
        return f"Namaste {name} ji, aapki dawai yaad dilana chahte hain."

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("patient.html",
        {"request": request, "patient_id": "P001", "name": PATIENTS["P001"]["name"]})

@app.get("/patient/{pid}", response_class=HTMLResponse)
async def patient_page(request: Request, pid: str):
    p = PATIENTS.get(pid, {"name": "Patient", "id": pid})
    return templates.TemplateResponse("patient.html",
        {"request": request, "patient_id": pid, "name": p["name"]})

@app.post("/verify-dose")
async def verify_dose(patient_id: str = Form(...), photo: UploadFile = File(...)):
    img_bytes = await photo.read()
    result = verify_pill(img_bytes)
    
    # Print the result to the terminal so you can see it working!
    print(f"\n=== Verification Result for {patient_id} ===\n{result}\n====================================\n")
    
    today = date.today().isoformat()
    if patient_id in DOSES:
        # Safely default to False if pill_visible isn't found
        DOSES[patient_id][today] = result.get("pill_visible", False)
    return JSONResponse(result)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    patients = get_all_patients()
    day_dates = [(date.today() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    return templates.TemplateResponse("dashboard.html",
        {"request": request, "patients": patients, "day_dates": day_dates})

@app.get("/asha/patient/{pid}", response_class=HTMLResponse)
async def asha_patient_page(request: Request, pid: str):
    all_patients = get_all_patients()
    patient_data = next((p for p in all_patients if p["id"] == pid), None)
    
    if not patient_data:
        raise HTTPException(status_code=404, detail="Patient not found")

    day_dates = [(date.today() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    
    return templates.TemplateResponse("templates_asha_patient.html", {
        "request": request,
        "patient": patient_data,
        "day_dates": day_dates
    })

@app.get("/sms/{pid}")
async def sms(pid: str):
    p = PATIENTS.get(pid, {"name": pid})
    missed = sum(1 for v in list(DOSES.get(pid,{}).values())[:7] if not v)
    msg = generate_sms(p["name"], missed)
    return {"message": msg}

@app.get("/health")
async def health():
    return {"status": "ok", "patients": len(PATIENTS)}