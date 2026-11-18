"""Local, review-led content workflow. No legacy records or demo seeding."""
import json
import os
import sqlite3
import uuid
import hashlib
import re
from io import BytesIO
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, Response, JSONResponse
from pydantic import BaseModel, Field
from services import workflow_access as access
from services import workflow_online as online
from services import workflow_permissions as permissions
from services import workflow_antivirus as antivirus
from services import workflow_accounts as accounts
from starlette.concurrency import run_in_threadpool

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
        connection.execute(
            "CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, kind TEXT NOT NULL, "
            "name TEXT NOT NULL, UNIQUE (kind, name))"
        )
        connection.execute("CREATE TABLE IF NOT EXISTS preferences (id INTEGER PRIMARY KEY, body TEXT NOT NULL)")
    access.initialize(connect)
    (DATA / "redacted").mkdir(parents=True, exist_ok=True)
    with connect() as db:
        permissions.initialize(db)
        accounts.initialize(db)
        for row in db.execute("SELECT id, body FROM records").fetchall():
            record = json.loads(row["body"])
            if "owner" not in record:
                record["owner"] = next((h["actor"] for h in record.get("history", []) if h.get("actor")), None)
                db.execute("UPDATE records SET body=? WHERE id=?", (json.dumps(record, ensure_ascii=False), row["id"]))
    yield


app = FastAPI(title="ساهر؛ گردش کار محتوا", lifespan=lifespan)
app.include_router(access.router)


@app.middleware("http")
async def authenticate(request: Request, call_next):
    if request.url.path.startswith("/api/v1/workflow"):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "مبدأ درخواست مجاز نیست"}, status_code=403)
        public = {"/api/v1/workflow/auth/status", "/api/v1/workflow/auth/setup",
                  "/api/v1/workflow/auth/login"}
        if request.url.path not in public:
            user = access.current_user(request)
            if user is None:
                return JSONResponse({"detail": "ابتدا وارد شوید"}, status_code=401)
            request.state.user = user
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/workflow"):
        response.headers["Cache-Control"] = "no-store"
    return response


class Preferences(BaseModel):
    categories: list[str] = Field(min_length=1, max_length=100)
    templates: list[str] = Field(min_length=1, max_length=50)
    sources: list[str] = Field(default_factory=list, max_length=100)


@app.get("/api/v1/workflow/settings")
def get_settings():
    with connect() as db:
        row = db.execute("SELECT body FROM preferences WHERE id=1").fetchone()
    return json.loads(row["body"]) if row else {
        "categories": ["اجتماعی", "اقتصادی", "امنیتی", "جاسوسی", "دفاعی", "دین و روحانیت",
                       "رزمایش", "سایبری", "سیاسی", "علم و فناوری", "فرهنگی", "هواگرد", "سایر"],
        "templates": ["گردش کار سازمانی", "بازبینی سیاست امنیتی", "بازبینی سیاست فرهنگی و اجتماعی"],
        "sources": [],
    }


@app.put("/api/v1/workflow/settings")
def save_settings(payload: Preferences, request: Request):
    if request.state.user["role"] != "admin":
        raise HTTPException(403, "دسترسی مدیر لازم است")
    values = {key: list(dict.fromkeys(item.strip() for item in items))
              for key, items in payload.model_dump().items()}
    if any(not item or len(item) > 200 for items in values.values() for item in items):
        raise HTTPException(422, "گزینه‌ها باید بین یک تا ۲۰۰ نویسه داشته باشند")
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO preferences VALUES (1, ?)", (json.dumps(values, ensure_ascii=False),))
    return values


@app.get("/api/v1/workflow/online")
def online_settings():
    return online.public_settings(online.read_settings(connect))


@app.put("/api/v1/workflow/online")
def update_online_settings(payload: online.OnlineSettings, request: Request):
    if request.state.user["role"] != "admin":
        raise HTTPException(403, "دسترسی مدیر لازم است")
    return online.save_settings(connect, payload)


class AnalysisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=60000)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400)


class PrivacyRequest(BaseModel):
    text: str = Field(max_length=1000000)
    terms: list[str] = Field(default_factory=list, max_length=100)


@app.post("/api/v1/workflow/privacy")
def redact_text(payload: PrivacyRequest):
    text = payload.text
    count = 0
    for term in sorted(set(payload.terms), key=len, reverse=True):
        if not term.strip() or len(term) > 200:
            raise HTTPException(422, "عبارت پوشاندن باید بین یک تا ۲۰۰ نویسه باشد")
        text, matches = re.subn(re.escape(term), "[پوشانده‌شده]", text)
        count += matches
    patterns = [
        r"(?<![\w.])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?!\w)",
        r"(?<!\d)(?:[+＋]?[9۹٩][8۸٨]|[0۰٠])[9۹٩]\d{9}(?!\d)",
        r"(?<!\d)\d{10}(?!\d)",
    ]
    for pattern in patterns:
        text, matches = re.subn(pattern, "[پوشانده‌شده]", text)
        count += matches
    return {"text": text, "count": count}


@app.post("/api/v1/workflow/online/analyze")
def analyze_online(payload: AnalysisRequest):
    values = online.read_settings(connect)
    return {"text": online.analyze(values, payload.text), "provider": values["provider"],
            "model": values["model"], "at": datetime.now(timezone.utc).isoformat()}


@app.post("/api/v1/workflow/online/search")
def search_online(payload: SearchRequest):
    return {"results": online.search(online.read_settings(connect), payload.query),
            "at": datetime.now(timezone.utc).isoformat()}


def read_record(record_id, request, write=False):
    with connect() as connection:
        row = connection.execute("SELECT body FROM records WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "محتوا یافت نشد")
        record = json.loads(row["body"])
        permissions.require_record(connection, request.state.user, record, write)
    return record


@app.get("/health")
def health():
    with connect() as connection:
        connection.execute("SELECT 1")
    return {"status": "healthy", "version": "workflow-4", "stages": STAGES}


@app.get("/api/v1/workflow")
def list_records(request: Request):
    with connect() as connection:
        rows = connection.execute("SELECT body FROM records ORDER BY rowid DESC").fetchall()
        records = [json.loads(row["body"]) for row in rows]
        return [{**r, "can_edit": permissions.record_allowed(connection, request.state.user, r, True)}
                for r in records if permissions.record_allowed(connection, request.state.user, r)]


@app.post("/api/v1/workflow", status_code=201)
async def create_record(request: Request, file: UploadFile = File(...), source: str = Form(...), permission: str = Form(...), case_id: str | None = Form(None)):
    if not source.strip() or not permission.strip():
        raise HTTPException(422, "منبع و مجوز پردازش را ثبت کنید")
    if case_id:
        with connect() as db:
            permissions.require_case(db, request.state.user, case_id, True)
    record_id = uuid.uuid4().hex
    filename = Path((file.filename or "file").replace("\\", "/")).name
    path = DATA / "originals" / record_id
    size = 0
    digest = hashlib.sha256()
    try:
        with path.open("wb") as output:
            while chunk := await file.read(65536):
                size += len(chunk)
                if size > 25 * 1024 * 1024:
                    raise HTTPException(413, "حداکثر اندازهٔ فایل ۲۵ مگابایت است")
                output.write(chunk)
                digest.update(chunk)
        if size == 0:
            raise HTTPException(422, "فایل خالی است")
        now = datetime.now(timezone.utc).isoformat()
        record = dict(id=record_id, title=filename, source=source.strip(), permission=permission.strip(),
                      stage=0, version=1, created=now, size=size, text="", category="", case_name="", case_id=None,
                      evidence="", unknowns="", analysis="", privacy_note="", reviewer="", decision="", template="",
                      history=[dict(at=now, action="ورود محتوا و ثبت منبع",
                                    actor=request.state.user["username"])])
        record["owner"] = request.state.user["username"]
        record["sha256"] = digest.hexdigest()
        record["antivirus"] = await run_in_threadpool(antivirus.scan_file, path)
        if record["antivirus"]["status"] == "clean":
            from services.ingestion.extractor import validate_file_signature
            valid, mime, detail = await run_in_threadpool(validate_file_signature, str(path), filename)
            record["file_check"] = {"signature_valid": valid, "mime": mime, "detail": detail}
        with connect() as connection:
            if case_id:
                permissions.require_case(connection, request.state.user, case_id, True)
                case = connection.execute("SELECT name FROM cases WHERE id=?", (case_id,)).fetchone()
                if not case:
                    raise HTTPException(404, "پرونده یافت نشد")
                record.update(case_id=case_id, case_name=case["name"])
            connection.execute("INSERT INTO records VALUES (?, ?)", (record_id, json.dumps(record, ensure_ascii=False)))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return record


class CaseCreate(BaseModel):
    kind: Literal["case", "event"]
    name: str = Field(max_length=200)


@app.get("/api/v1/workflow/cases")
def list_cases(request: Request):
    with connect() as connection:
        rows = connection.execute("SELECT id, kind, name FROM cases ORDER BY name, kind").fetchall()
        return [dict(row) for row in rows if permissions.case_allowed(connection, request.state.user, row["id"])]


@app.post("/api/v1/workflow/cases", status_code=201)
def create_case(payload: CaseCreate, request: Request):
    name = payload.name.strip()
    if not name:
        raise HTTPException(422, "نام پرونده یا رویداد را وارد کنید")
    item = {"id": uuid.uuid4().hex, "kind": payload.kind, "name": name}
    try:
        with connect() as connection:
            connection.execute(
                "INSERT INTO cases (id, kind, name) VALUES (:id, :kind, :name)", item
            )
            connection.execute("INSERT INTO case_members VALUES (?, ?, 'editor')", (item["id"], request.state.user["username"]))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "این نام قبلاً برای همین نوع ثبت شده است")
    return item


class Update(BaseModel):
    version: int
    stage: int = Field(ge=0, le=3)
    text: str = ""
    category: str = ""
    case_name: str = ""
    case_id: str | None = None
    evidence: str = ""
    unknowns: str = ""
    analysis: str = ""
    privacy_note: str = ""
    reviewer: str = ""
    decision: str = ""
    template: str = ""


def admin_only(request):
    if request.state.user["role"] != "admin":
        raise HTTPException(403, "دسترسی مدیر لازم است")


class Membership(BaseModel):
    permission: Literal["viewer", "editor"]


@app.get("/api/v1/workflow/cases/{case_id}/members")
def case_members(case_id: str, request: Request):
    admin_only(request)
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT username, permission FROM case_members WHERE case_id=?", (case_id,))]


def change_member(case_id, username, request, permission=None):
    admin_only(request)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM cases WHERE id=?", (case_id,)).fetchone():
            raise HTTPException(404, "پرونده یافت نشد")
        if not db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise HTTPException(404, "کاربر یافت نشد")
        db.execute("DELETE FROM case_members WHERE case_id=? AND username=?", (case_id, username))
        if permission:
            db.execute("INSERT INTO case_members VALUES (?, ?, ?)", (case_id, username, permission))
        db.execute("CREATE TABLE IF NOT EXISTS case_access_audit (at TEXT, actor TEXT, case_id TEXT, username TEXT, permission TEXT)")
        db.execute("INSERT INTO case_access_audit VALUES (?, ?, ?, ?, ?)",
                   (datetime.now(timezone.utc).isoformat(), request.state.user["username"], case_id, username, permission))
    return {"ok": True}


@app.put("/api/v1/workflow/cases/{case_id}/members/{username}")
def grant_member(case_id: str, username: str, payload: Membership, request: Request):
    return change_member(case_id, username, request, payload.permission)


@app.delete("/api/v1/workflow/cases/{case_id}/members/{username}")
def revoke_member(case_id: str, username: str, request: Request):
    return change_member(case_id, username, request)


class VersionRequest(BaseModel):
    version: int = Field(ge=1)


@app.get("/api/v1/workflow/accounts")
def account_folders(request: Request):
    folders = {}
    pending = 0
    with connect() as db:
        for row in db.execute("SELECT body FROM records"):
            record = json.loads(row["body"])
            if not permissions.record_allowed(db, request.state.user, record):
                continue
            account = record.get("account")
            if not account or not record.get("account_id"):
                if record.get("file_check", {}).get("mime", "").startswith("image/"):
                    pending += 1
                continue
            key = record["account_id"]
            folder = folders.setdefault(key, {"id": key, "platform": account["platform"], "handle": account["handle"],
                                               "case_id": record.get("case_id"), "case_name": record.get("case_name", ""),
                                               "total": 0, "categories": {}})
            folder["total"] += 1
            category = record.get("category") or ""
            folder["categories"][category] = folder["categories"].get(category, 0) + 1
    return {"folders": sorted(folders.values(), key=lambda folder: (folder["platform"], folder["handle"])), "pending": pending}


@app.post("/api/v1/workflow/{record_id}/analyze-image")
def analyze_account_image(record_id: str, payload: VersionRequest, request: Request):
    record = read_record(record_id, request, True)
    if payload.version != record["version"]:
        raise HTTPException(409, "محتوا تغییر کرده است")
    antivirus.require_clean(record, DATA / "originals" / record_id)
    if not record.get("file_check", {}).get("mime", "").startswith("image/"):
        raise HTTPException(415, "این عملیات فقط برای عکس است")
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(DATA / "originals" / record_id) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise HTTPException(415, "برای ورود گروهی، عکس ثابت و تک‌فریمی انتخاب کنید")
            if image.width * image.height > 24_000_000:
                raise HTTPException(413, "برای متن‌خوانی گروهی، عکس باید حداکثر ۲۴ میلیون پیکسل باشد")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise HTTPException(422, "عکس قابل متن‌خوانی نیست") from error
    result = extract(record_id, request)
    text = result["text"]
    return persist_security(record, request, {"text": text, "account_candidates": accounts.candidates(text),
                                              "stage": min(record["stage"], 1)},
                            "متن‌خوانی عکس و پیشنهاد آی‌دی؛ بدون تأیید اتصال")


@app.get("/api/v1/workflow/{record_id}/preview")
def preview_account_image(record_id: str, request: Request):
    record = read_record(record_id, request)
    source = DATA / "originals" / record_id
    antivirus.require_clean(record, source)
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        with Image.open(source) as image:
            if getattr(image, "n_frames", 1) != 1 or image.width * image.height > 24_000_000:
                raise HTTPException(415, "پیش‌نمایش فقط برای عکس ثابت تا ۲۴ میلیون پیکسل است")
            normalized = ImageOps.exif_transpose(image).convert("RGBA")
            result = Image.new("RGBA", normalized.size, "white")
            result.alpha_composite(normalized)
            result = result.convert("RGB")
            result.thumbnail((1200, 1200))
            result.info.clear()
            output = BytesIO()
            result.save(output, "JPEG", quality=85)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise HTTPException(422, "عکس قابل پیش‌نمایش نیست") from error
    return Response(output.getvalue(), media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff"})


class AccountAssignment(VersionRequest):
    platform: Literal["instagram", "telegram", "x", "tiktok", "youtube", "facebook"]
    handle: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
    category: str = Field(default="", max_length=200)


@app.post("/api/v1/workflow/{record_id}/organize")
def organize_account_image(record_id: str, payload: AccountAssignment, request: Request):
    record = read_record(record_id, request, True)
    antivirus.require_clean(record, DATA / "originals" / record_id)
    if not record.get("file_check", {}).get("mime", "").startswith("image/"):
        raise HTTPException(415, "این عملیات فقط برای عکس است")
    if payload.category and payload.category not in get_settings()["categories"]:
        raise HTTPException(422, "موضوع باید از فهرست تنظیم‌شده انتخاب شود")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT body FROM records WHERE id=?", (record_id,)).fetchone()
        if not current:
            raise HTTPException(404, "محتوا یافت نشد")
        record = json.loads(current["body"])
        permissions.require_record(db, request.state.user, record, True)
        if record["version"] != payload.version:
            raise HTTPException(409, "محتوا تغییر کرده است")
        scope = "case:" + record["case_id"] if record.get("case_id") else ("owner:" + record["owner"] if record.get("owner") else "legacy")
        handle = payload.handle.lower()
        db.execute("INSERT OR IGNORE INTO image_accounts VALUES (?, ?, ?, ?)", (uuid.uuid4().hex, scope, payload.platform, handle))
        account = db.execute("SELECT id FROM image_accounts WHERE scope=? AND platform=? AND handle=?", (scope, payload.platform, handle)).fetchone()
        now = datetime.now(timezone.utc).isoformat()
        before = {"account_id": record.get("account_id"), "category": record.get("category")}
        record.update(account_id=account["id"], account={"platform": payload.platform, "handle": handle,
                      "confirmed_by": request.state.user["username"], "confirmed_at": now}, category=payload.category,
                      decision="", review_verified=False, version=record["version"]+1)
        record["history"].append({"at": now, "actor": request.state.user["username"],
                                  "action": "تأیید دستی حسابِ ذکرشده و موضوع عکس؛ بدون احراز هویت فرد",
                                  "changes": {"before": before, "after": {"account_id": account["id"], "category": payload.category}}})
        db.execute("UPDATE records SET body=? WHERE id=?", (json.dumps(record, ensure_ascii=False), record_id))
    return record


class MaskRequest(VersionRequest):
    boxes: list[list[float]] = Field(default_factory=list, max_length=100)


@app.post("/api/v1/workflow/{record_id}/redact")
def redact_image(record_id: str, payload: MaskRequest, request: Request):
    record = read_record(record_id, request, True)
    if record["version"] != payload.version:
        raise HTTPException(409, "محتوا تغییر کرده است")
    source = DATA / "originals" / record_id
    antivirus.require_clean(record, source)
    from services.workflow_images import mask
    target = DATA / "redacted" / (uuid.uuid4().hex + ".png")
    try:
        result = mask(source, target, payload.boxes, record.get("redaction"))
        return persist_security(record, request, {"redaction": result, "stage": min(record["stage"], 1)}, "پوشاندن چهره و پلاک و نواحی انتخابی تصویر")
    except Exception:
        target.unlink(missing_ok=True)
        raise


@app.post("/api/v1/workflow/{record_id}/redact/confirm")
def confirm_image(record_id: str, payload: VersionRequest, request: Request):
    record = read_record(record_id, request, True)
    if record["version"] != payload.version:
        raise HTTPException(409, "محتوا تغییر کرده است")
    antivirus.require_clean(record, DATA / "originals" / record_id)
    result = record.get("redaction")
    if not result:
        raise HTTPException(422, "ابتدا تصویر پوشانده‌شده را بسازید")
    target = DATA / "redacted" / result["filename"]
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != result["sha256"]:
        raise HTTPException(409, "نسخهٔ پوشانده‌شده تغییر کرده است")
    result = {**result, "confirmed": True, "confirmed_by": request.state.user["username"]}
    return persist_security(record, request, {"redaction": result}, "تأیید بازبینی تصویر پوشانده‌شده")


@app.get("/api/v1/workflow/{record_id}/redacted")
def redacted_image(record_id: str, request: Request):
    record = read_record(record_id, request)
    antivirus.require_clean(record, DATA / "originals" / record_id)
    result = record.get("redaction")
    if not result:
        raise HTTPException(404, "نسخهٔ پوشانده‌شده یافت نشد")
    target = DATA / "redacted" / result["filename"]
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != result["sha256"]:
        raise HTTPException(409, "نسخهٔ پوشانده‌شده تغییر کرده است")
    return FileResponse(target, media_type="image/png", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def persist_security(record, request, changes, action):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT body FROM records WHERE id=?", (record["id"],)).fetchone()
        if not row:
            raise HTTPException(404, "محتوا یافت نشد")
        current = json.loads(row["body"])
        permissions.require_record(db, request.state.user, current, True)
        if current["version"] != record["version"]:
            raise HTTPException(409, "محتوا تغییر کرده است؛ دوباره بارگذاری کنید")
        current.update(changes)
        current.update(version=current["version"] + 1, decision="", review_verified=False)
        current["history"].append({"at": datetime.now(timezone.utc).isoformat(), "actor": request.state.user["username"], "action": action})
        db.execute("UPDATE records SET body=? WHERE id=?", (json.dumps(current, ensure_ascii=False), current["id"]))
    return current


@app.post("/api/v1/workflow/{record_id}/scan")
def scan_original(record_id: str, payload: VersionRequest, request: Request):
    record = read_record(record_id, request, True)
    if record["version"] != payload.version:
        raise HTTPException(409, "محتوا تغییر کرده است")
    path = DATA / "originals" / record_id
    result = antivirus.scan_file(path)
    if result["status"] == "clean" and result["sha256"] != record["sha256"]:
        result["status"] = "changed"
    changes = {"antivirus": result}
    if result["status"] == "clean":
        from services.ingestion.extractor import validate_file_signature
        valid, mime, detail = validate_file_signature(str(path), record["title"])
        changes["file_check"] = {"signature_valid": valid, "mime": mime, "detail": detail}
    else:
        changes.update(stage=0, redaction=None)
    return persist_security(record, request, changes, "اسکن ضدبدافزار: " + result["status"])


@app.put("/api/v1/workflow/{record_id}")
def update_record(record_id: str, payload: Update, request: Request):
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT body FROM records WHERE id = ?", (record_id,)).fetchone()
        if not row:
            raise HTTPException(404, "محتوا یافت نشد")
        record = json.loads(row["body"])
        permissions.require_record(connection, request.state.user, record, True)
        if payload.version != record["version"]:
            raise HTTPException(409, "این محتوا تغییر کرده است؛ صفحه را تازه کنید")
        if payload.stage > record["stage"] + 1:
            raise HTTPException(422, "مراحل را به ترتیب بررسی کنید")
        if payload.stage > 0:
            antivirus.require_clean(record, DATA / "originals" / record_id)
        if payload.stage >= 2 and record.get("file_check", {}).get("mime", "").startswith("image/"):
            if not (record.get("redaction") or {}).get("confirmed"):
                raise HTTPException(422, "نسخهٔ پوشانده‌شدهٔ تصویر را ایجاد و بازبینی کنید")
        if payload.stage >= 2 and not payload.privacy_note.strip():
            raise HTTPException(422, "نتیجهٔ بررسی سلامت و حریم خصوصی را ثبت کنید")
        if payload.stage >= 3 and (not payload.category.strip() or not payload.evidence.strip()):
            raise HTTPException(422, "موضوع و شواهد بررسی را ثبت کنید")
        changes = payload.model_dump(exclude={"version"})
        if "case_id" not in payload.model_fields_set:
            changes["case_id"] = record.get("case_id")
        if changes["case_id"] != record.get("case_id") and request.state.user["role"] != "admin" and record.get("owner") != request.state.user["username"]:
            raise HTTPException(403, "انتقال محتوا فقط توسط مالک یا مدیر مجاز است")
        if changes["case_id"] != record.get("case_id"):
            changes.update(account_id=None, account=None)
        if changes["case_id"] is not None:
            case = connection.execute(
                "SELECT name FROM cases WHERE id = ?", (changes["case_id"],)
            ).fetchone()
            if case is None:
                raise HTTPException(422, "پرونده یا رویداد انتخاب‌شده یافت نشد")
            if changes["case_id"] != record.get("case_id"):
                permissions.require_case(connection, request.state.user, changes["case_id"], True)
            changes["case_name"] = case["name"]
        review_fields = ("text", "category", "case_id", "case_name", "evidence", "unknowns", "analysis", "privacy_note")
        review_changed = any(changes[key] != record.get(key) for key in review_fields)
        if payload.stage != 3 or record["stage"] != 3 or review_changed:
            changes["decision"] = ""
        if changes["decision"].strip() and not payload.template.strip():
            raise HTTPException(422, "قالب خروجی لازم است")
        if changes["decision"].strip():
            if request.state.user["role"] not in ("admin", "reviewer"):
                raise HTTPException(403, "ثبت تصمیم به نقش بازبین نیاز دارد")
            changes["reviewer"] = request.state.user["username"]
            changes["review_verified"] = True
        else:
            changes["review_verified"] = False
        action = "ثبت اصلاحات" if payload.stage == record["stage"] else f"انتقال به {STAGES[payload.stage]}"
        if record["decision"].strip() and not changes["decision"].strip():
            action += " و ابطال تصمیم بازبین"
        field_changes = {key: {"before": record.get(key), "after": value}
                         for key, value in changes.items() if value != record.get(key)}
        record.update(changes)
        record["version"] += 1
        record["history"].append(dict(at=datetime.now(timezone.utc).isoformat(), action=action,
                                     actor=request.state.user["username"], changes=field_changes))
        connection.execute("UPDATE records SET body = ? WHERE id = ?", (json.dumps(record, ensure_ascii=False), record_id))
    return record


@app.post("/api/v1/workflow/{record_id}/inspect")
def inspect_file(record_id: str, request: Request):
    record = read_record(record_id, request)
    path = DATA / "originals" / record["id"]
    antivirus.require_clean(record, path)
    if not path.is_file():
        raise HTTPException(404, "اصل فایل یافت نشد")
    from services.ingestion.extractor import validate_file_signature
    valid, mime, error = validate_file_signature(str(path), record["title"])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"signature_valid": valid, "mime": mime, "detail": error,
            "sha256": digest, "integrity": digest == record.get("sha256") if record.get("sha256") else None,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "checked_by": request.state.user["username"],
            "scope": "بررسی ساختار و یکپارچگی فایل؛ نتیجهٔ ضدبدافزار جداگانه ثبت شده است"}


@app.get("/api/v1/workflow/{record_id}/original")
def download_original(record_id: str, request: Request):
    record = read_record(record_id, request)
    path = DATA / "originals" / record["id"]
    antivirus.require_clean(record, path)
    if not path.is_file():
        raise HTTPException(404, "اصل فایل یافت نشد")
    return FileResponse(
        path, filename=record["title"], media_type="application/octet-stream",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@app.post("/api/v1/workflow/{record_id}/extract")
def extract(record_id: str, request: Request):
    record = read_record(record_id, request, True)
    path = DATA / "originals" / record_id
    antivirus.require_clean(record, path)
    from services.ingestion.extractor import extract_document_content, validate_file_signature
    valid, mime, error = validate_file_signature(str(path), record["title"])
    if not valid:
        raise HTTPException(422, error or "ساختار فایل برای استخراج معتبر نیست")
    result = extract_document_content(str(path), mime, record["title"])
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
def export_record(record_id: str, request: Request, format: Literal["json", "docx"] = "json"):
    record = read_record(record_id, request)
    antivirus.require_clean(record, DATA / "originals" / record_id)
    if record["stage"] != 3 or not record["decision"].strip() or not record.get("review_verified"):
        raise HTTPException(422, "ابتدا تصمیم بازبین را ثبت کنید")
    image_path = None
    if record.get("file_check", {}).get("mime", "").startswith("image/"):
        redaction = record.get("redaction") or {}
        if not redaction.get("confirmed"):
            raise HTTPException(422, "نسخهٔ پوشانده‌شدهٔ تصویر را بازبینی کنید")
        image_path = DATA / "redacted" / redaction["filename"]
        if not image_path.is_file() or hashlib.sha256(image_path.read_bytes()).hexdigest() != redaction["sha256"]:
            raise HTTPException(409, "تصویر پوشانده‌شده معتبر نیست")
    if format == "docx":
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.shared import Pt, RGBColor
        document = Document()
        for name in ("Normal", "Title", "Heading 1"):
            document.styles[name].font.name = "Arial"
            document.styles[name].font.color.rgb = RGBColor(0, 0, 0)
        document.styles["Normal"].font.size = Pt(12)
        document.add_paragraph(record["title"], "Title")
        document.add_paragraph(record["decision"])
        if image_path:
            from docx.shared import Inches
            document.add_picture(str(image_path), width=Inches(6))
        for key, label in (("template", "مسیر بازبینی"), ("source", "منبع"),
                           ("permission", "مجوز پردازش"), ("category", "موضوع"),
                           ("case_name", "پرونده یا رویداد"), ("reviewer", "بازبین"),
                           ("text", "متن محتوا"), ("evidence", "شواهد"), ("analysis", "یادداشت تحلیل"),
                           ("unknowns", "موارد نامشخص"), ("privacy_note", "سلامت و حریم خصوصی")):
            document.add_paragraph(label, "Heading 1")
            document.add_paragraph(record.get(key) or "ثبت نشده")
        document.add_paragraph("سابقه اقدامات", "Heading 1")
        for item in record["history"]:
            document.add_paragraph(f'{item["at"]} · {item.get("actor", "")} · {item["action"]}')
        for paragraph in document.paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            paragraph._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
        output = BytesIO()
        document.save(output)
        return Response(output.getvalue(),
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers={"Content-Disposition": f'attachment; filename="saher-{record_id}.docx"'})
    return Response(json.dumps(record, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="saher-{record_id}.json"'})
