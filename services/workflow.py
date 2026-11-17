"""Local, review-led content workflow. No legacy records or demo seeding."""
import json
import mimetypes
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

DATA = Path(os.environ.get("SAHER_WORKFLOW_DATA", str(Path(__file__).resolve().parents[1] / "data")))
STAGES = ["ورودی‌ها", "آماده‌سازی", "بررسی محتوا", "خروجی و بازبینی"]


def connect():
    connection = sqlite3.connect(DATA / "workflow.db", timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


@asynccontextmanager
async def lifespan(app):
    (DATA / "originals").mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
    yield


app = FastAPI(title="ساهر؛ گردش کار محتوا", lifespan=lifespan)


def read_record(record_id):
    with connect() as connection:
        row = connection.execute("SELECT body FROM records WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "محتوا یافت نشد")
    return json.loads(row["body"])


@app.get("/health")
def health():
    with connect() as connection:
        connection.execute("SELECT 1")
    return {"status": "healthy", "version": "workflow-1", "stages": STAGES}


@app.get("/api/v1/workflow")
def list_records():
    with connect() as connection:
        rows = connection.execute("SELECT body FROM records ORDER BY rowid DESC").fetchall()
    return [json.loads(row["body"]) for row in rows]


@app.post("/api/v1/workflow", status_code=201)
async def create_record(file: UploadFile = File(...), source: str = Form(...), permission: str = Form(...)):
    if not source.strip() or not permission.strip():
        raise HTTPException(422, "منبع و مجوز پردازش را ثبت کنید")
    record_id = uuid.uuid4().hex
    filename = Path((file.filename or "file").replace("\\", "/")).name
    path = DATA / "originals" / record_id
    size = 0
    try:
        with path.open("wb") as output:
            while chunk := await file.read(65536):
                size += len(chunk)
                if size > 25 * 1024 * 1024:
                    raise HTTPException(413, "حداکثر اندازهٔ فایل ۲۵ مگابایت است")
                output.write(chunk)
        if size == 0:
            raise HTTPException(422, "فایل خالی است")
        now = datetime.now(timezone.utc).isoformat()
        record = dict(id=record_id, title=filename, source=source.strip(), permission=permission.strip(),
                      stage=0, version=1, created=now, size=size, text="", category="", case_name="",
                      evidence="", unknowns="", privacy_note="", reviewer="", decision="", template="",
                      history=[dict(at=now, action="ورود محتوا و ثبت منبع")])
        with connect() as connection:
            connection.execute("INSERT INTO records VALUES (?, ?)", (record_id, json.dumps(record, ensure_ascii=False)))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return record


class Update(BaseModel):
    version: int
    stage: int = Field(ge=0, le=3)
    text: str = ""
    category: str = ""
    case_name: str = ""
    evidence: str = ""
    unknowns: str = ""
    privacy_note: str = ""
    reviewer: str = ""
    decision: str = ""
    template: str = ""


@app.put("/api/v1/workflow/{record_id}")
def update_record(record_id: str, payload: Update):
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT body FROM records WHERE id = ?", (record_id,)).fetchone()
        if not row:
            raise HTTPException(404, "محتوا یافت نشد")
        record = json.loads(row["body"])
        if payload.version != record["version"]:
            raise HTTPException(409, "این محتوا تغییر کرده است؛ صفحه را تازه کنید")
        if payload.stage > record["stage"] + 1:
            raise HTTPException(422, "مراحل را به ترتیب بررسی کنید")
        if payload.stage >= 2 and not payload.privacy_note.strip():
            raise HTTPException(422, "نتیجهٔ بررسی سلامت و حریم خصوصی را ثبت کنید")
        if payload.stage >= 3 and (not payload.category.strip() or not payload.evidence.strip()):
            raise HTTPException(422, "موضوع و شواهد بررسی را ثبت کنید")
        if payload.decision.strip() and (not payload.reviewer.strip() or not payload.template.strip()):
            raise HTTPException(422, "نام بازبین و قالب خروجی لازم است")
        action = "ثبت اصلاحات" if payload.stage == record["stage"] else f"انتقال به {STAGES[payload.stage]}"
        record.update(payload.model_dump(exclude={"version"}))
        record["version"] += 1
        record["history"].append(dict(at=datetime.now(timezone.utc).isoformat(), action=action))
        connection.execute("UPDATE records SET body = ? WHERE id = ?", (json.dumps(record, ensure_ascii=False), record_id))
    return record


@app.post("/api/v1/workflow/{record_id}/extract")
def extract(record_id: str):
    record = read_record(record_id)
    path = DATA / "originals" / record_id
    from services.ingestion.extractor import extract_document_content
    result = extract_document_content(str(path), mimetypes.guess_type(record["title"])[0] or "", record["title"])
    text = result.extracted_text
    if result.needs_ocr_pages:
        from services.ocr.tesseract_engine import TesseractOCREngine
        from services.ingestion.extractor import render_pdf_page_to_pil
        engine = TesseractOCREngine()
        sections = [text] if text else []
        for page in result.needs_ocr_pages:
            image = render_pdf_page_to_pil(str(path), page) if record["title"].lower().endswith(".pdf") else str(path)
            sections.append(engine.recognize_image(image, page_number=page).raw_text)
        text = "\n\n".join(sections)
    if not text.strip():
        raise HTTPException(422, "متن قابل استخراج پیدا نشد؛ متن را دستی ثبت کنید")
    return {"text": text, "version": record["version"]}


@app.get("/api/v1/workflow/{record_id}/export")
def export_record(record_id: str):
    record = read_record(record_id)
    if record["stage"] != 3 or not record["decision"].strip():
        raise HTTPException(422, "ابتدا تصمیم بازبین را ثبت کنید")
    return Response(json.dumps(record, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="saher-{record_id}.json"'})
