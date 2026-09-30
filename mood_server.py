import csv
import os
import threading
from datetime import date, datetime
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

DATA_DIR = "data"
LOG_FILE = os.path.join(DATA_DIR, "mood_log.csv")
EVENT_FILE = os.path.join(DATA_DIR, "events.csv")
SPIKE_FILE = os.path.join(DATA_DIR, "event_spikes.csv")
LOG_LOCK = threading.Lock()
API_TOKEN = os.getenv("EMBER_API_TOKEN", "ember-local-dev-token")

EVENT_FIELDS = ["id", "name", "category", "start_date", "end_date", "notes"]
SPIKE_FIELDS = ["event_id", "date", "severity", "notes"]

FIELDS = [
    "date",
    "session",
    # Morning
    "rested",
    "early_waking",
    "less_sleep_fine",
    "thought_speed_morning",
    "classification_night",
    # Evening
    "energy",
    "new_projects",
    "effortful",
    "concentration",
    "mood",
    "irritable",
    "impulsive",
    "withdrew",
    "alcohol",
    "illness",
    "travel",
    "life_stress",
    "classification_day",
    "notes",
]

class MorningEntry(BaseModel):
    rested: int
    early_waking: str
    less_sleep_fine: str
    thought_speed_morning: int
    classification_night: str

class EveningEntry(BaseModel):
    energy: int
    new_projects: str
    effortful: str
    concentration: int
    mood: int
    irritable: str
    impulsive: str
    withdrew: str
    alcohol: str
    illness: str
    travel: str
    life_stress: str
    classification_day: str
    notes: Optional[str] = ""

class BackfillMorningEntry(MorningEntry):
    date: str

class BackfillEveningEntry(EveningEntry):
    date: str

class NewEvent(BaseModel):
    name: str
    category: str  # relocation | interpersonal | work | health | other
    start_date: str
    end_date: Optional[str] = ""
    notes: Optional[str] = ""

class EventUpdate(BaseModel):
    end_date: Optional[str] = None
    notes: Optional[str] = None

class NewSpike(BaseModel):
    date: str
    severity: int  # 1-5
    notes: Optional[str] = ""


def _require_auth(authorization: Optional[str] = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    if not token or token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bearer token")

def _validate_date(d: str, field: str = "date"):
    try:
        datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        return JSONResponse(status_code=400, content={"message": f"{field} must be YYYY-MM-DD"})
    return None

def ensure_events():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(EVENT_FILE):
        with open(EVENT_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=EVENT_FIELDS).writeheader()
    if not os.path.exists(SPIKE_FILE):
        with open(SPIKE_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=SPIKE_FIELDS).writeheader()

def read_events() -> list:
    ensure_events()
    with open(EVENT_FILE, "r") as f:
        return list(csv.DictReader(f))

def next_event_id() -> int:
    rows = read_events()
    if not rows:
        return 1
    return max(int(r["id"]) for r in rows) + 1

def read_spikes(event_id: Optional[int] = None) -> list:
    ensure_events()
    with open(SPIKE_FILE, "r") as f:
        rows = list(csv.DictReader(f))
    if event_id is not None:
        rows = [r for r in rows if r["event_id"] == str(event_id)]
    return rows

def ensure_log():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()

def already_logged(today: str, session: str) -> bool:
    if not os.path.exists(LOG_FILE):
        return False
    with open(LOG_FILE, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["date"] == today and row["session"] == session:
                return True
    return False

def write_row(row: dict):
    ensure_log()
    full_row = {field: row.get(field, "") for field in FIELDS}
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writerow(full_row)

def submit_mood_row(today: str, session: str, data: dict, already_exists_message: str):
    with LOG_LOCK:
        if already_logged(today, session):
            return JSONResponse(status_code=409, content={"message": already_exists_message})
        write_row({"date": today, "session": session, **data})
    return {"message": "Logged", "date": today, "session": session}

@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <html><body style="font-family:monospace;background:#0a0a0a;color:#e8e4dc;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;gap:20px;">
    <div style="font-size:13px;letter-spacing:0.2em;color:#e85d26;">EMBER</div>
    <a href="/morning" style="color:#e8e4dc;font-size:14px;">Morning check-in</a>
    <a href="/evening" style="color:#e8e4dc;font-size:14px;">Evening check-in</a>
    </body></html>
    """

@app.get("/morning", response_class=HTMLResponse)
def morning_form():
    with open("mood_form_morning.html") as f:
        return f.read()

@app.get("/evening", response_class=HTMLResponse)
def evening_form():
    with open("mood_form_evening.html") as f:
        return f.read()

@app.post("/submit/morning")
def submit_morning(entry: MorningEntry, _: None = Depends(_require_auth)):
    today = date.today().isoformat()
    return submit_mood_row(today, "morning", entry.dict(), "Morning entry already logged today.")

@app.post("/submit/evening")
def submit_evening(entry: EveningEntry, _: None = Depends(_require_auth)):
    today = date.today().isoformat()
    return submit_mood_row(today, "evening", entry.dict(), "Evening entry already logged today.")

@app.post("/submit/backfill/morning")
def backfill_morning(entry: BackfillMorningEntry, _: None = Depends(_require_auth)):
    try:
        datetime.strptime(entry.date, "%Y-%m-%d")
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "date must be YYYY-MM-DD"})
    data = entry.dict()
    target_date = data.pop("date")
    return submit_mood_row(target_date, "morning", data, f"Morning entry already exists for {target_date}.")

@app.post("/submit/backfill/evening")
def backfill_evening(entry: BackfillEveningEntry, _: None = Depends(_require_auth)):
    try:
        datetime.strptime(entry.date, "%Y-%m-%d")
    except ValueError:
        return JSONResponse(status_code=400, content={"message": "date must be YYYY-MM-DD"})
    data = entry.dict()
    target_date = data.pop("date")
    return submit_mood_row(target_date, "evening", data, f"Evening entry already exists for {target_date}.")

@app.get("/history")
def history(_: None = Depends(_require_auth)):
    ensure_log()
    rows = []
    with open(LOG_FILE, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return {"entries": rows[-14:]}

# --- Events ---

@app.post("/events", status_code=201)
def create_event(event: NewEvent, _: None = Depends(_require_auth)):
    err = _validate_date(event.start_date, "start_date")
    if err:
        return err
    if event.end_date:
        err = _validate_date(event.end_date, "end_date")
        if err:
            return err
    ensure_events()
    eid = next_event_id()
    row = {"id": eid, "name": event.name, "category": event.category,
           "start_date": event.start_date, "end_date": event.end_date or "",
           "notes": event.notes or ""}
    with open(EVENT_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=EVENT_FIELDS).writerow(row)
    return {"message": "Event created", "id": eid}

@app.get("/events")
def list_events(_: None = Depends(_require_auth)):
    return {"events": read_events()}

@app.get("/events/{event_id}")
def get_event(event_id: int, _: None = Depends(_require_auth)):
    matches = [r for r in read_events() if r["id"] == str(event_id)]
    if not matches:
        return JSONResponse(status_code=404, content={"message": "Event not found"})
    event = matches[0]
    event["spikes"] = read_spikes(event_id)
    return event

@app.patch("/events/{event_id}")
def update_event(event_id: int, update: EventUpdate, _: None = Depends(_require_auth)):
    rows = read_events()
    found = False
    for row in rows:
        if row["id"] == str(event_id):
            if update.end_date is not None:
                err = _validate_date(update.end_date, "end_date")
                if err:
                    return err
                row["end_date"] = update.end_date
            if update.notes is not None:
                row["notes"] = update.notes
            found = True
            break
    if not found:
        return JSONResponse(status_code=404, content={"message": "Event not found"})
    with open(EVENT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return {"message": "Event updated"}

@app.post("/events/{event_id}/spikes", status_code=201)
def add_spike(event_id: int, spike: NewSpike, _: None = Depends(_require_auth)):
    err = _validate_date(spike.date)
    if err:
        return err
    if not 1 <= spike.severity <= 5:
        return JSONResponse(status_code=400, content={"message": "severity must be 1-5"})
    matches = [r for r in read_events() if r["id"] == str(event_id)]
    if not matches:
        return JSONResponse(status_code=404, content={"message": "Event not found"})
    ensure_events()
    row = {"event_id": event_id, "date": spike.date,
           "severity": spike.severity, "notes": spike.notes or ""}
    with open(SPIKE_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=SPIKE_FIELDS).writerow(row)
    return {"message": "Spike logged", "event_id": event_id, "date": spike.date}

@app.get("/events/{event_id}/spikes")
def get_spikes(event_id: int, _: None = Depends(_require_auth)):
    matches = [r for r in read_events() if r["id"] == str(event_id)]
    if not matches:
        return JSONResponse(status_code=404, content={"message": "Event not found"})
    return {"event_id": event_id, "spikes": read_spikes(event_id)}
