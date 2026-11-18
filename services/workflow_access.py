"""Persistent local accounts and browser sessions for the workflow API."""
import hashlib
import hmac
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/workflow/auth")
connect = None


def initialize(database_connect):
    global connect
    connect = database_connect
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT NOT NULL, role TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, username TEXT NOT NULL, expires REAL NOT NULL)")


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + "." + digest


def current_user(request):
    token = request.cookies.get("saher_session", "")
    with connect() as db:
        row = db.execute(
            "SELECT u.username, u.role FROM sessions s JOIN users u ON u.username=s.username "
            "WHERE s.token=? AND s.expires>?",
            (hashlib.sha256(token.encode()).hexdigest(), time.time()),
        ).fetchone()
    return dict(row) if row else None


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=256)


class UserCreate(Credentials):
    role: str = Field(pattern=r"^(admin|reviewer|editor)$")


@router.get("/status")
def status(request: Request):
    with connect() as db:
        configured = db.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None
    return {"configured": configured, "user": current_user(request)}


@router.post("/setup", status_code=201)
def setup(payload: Credentials):
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            raise HTTPException(409, "مدیر اولیه قبلاً ثبت شده است")
        db.execute("INSERT INTO users VALUES (?, ?, 'admin')",
                   (payload.username, password_hash(payload.password)))
    return {"username": payload.username, "role": "admin"}


@router.post("/login")
def login(payload: Credentials, response: Response):
    with connect() as db:
        row = db.execute("SELECT * FROM users WHERE username=?", (payload.username,)).fetchone()
        stored = row["password"] if row else password_hash("invalid credential")
        matches = hmac.compare_digest(stored, password_hash(payload.password, stored.split(".")[0]))
        if not row or not matches:
            raise HTTPException(401, "نام کاربری یا گذرواژه صحیح نیست")
        token = secrets.token_urlsafe(32)
        db.execute("DELETE FROM sessions WHERE expires<=?", (time.time(),))
        db.execute("INSERT INTO sessions VALUES (?, ?, ?)",
                   (hashlib.sha256(token.encode()).hexdigest(), row["username"], time.time() + 28800))
    response.set_cookie("saher_session", token, httponly=True, samesite="strict", max_age=28800)
    return {"username": row["username"], "role": row["role"]}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("saher_session", "")
    with connect() as db:
        db.execute("DELETE FROM sessions WHERE token=?", (hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie("saher_session")
    return {"ok": True}


@router.get("/users")
def users(request: Request):
    if (current_user(request) or {}).get("role") != "admin":
        raise HTTPException(403, "دسترسی مدیر لازم است")
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT username, role FROM users ORDER BY username")]


@router.post("/users", status_code=201)
def add_user(payload: UserCreate, request: Request):
    if (current_user(request) or {}).get("role") != "admin":
        raise HTTPException(403, "دسترسی مدیر لازم است")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM users WHERE username=?", (payload.username,)).fetchone():
            raise HTTPException(409, "نام کاربری تکراری است")
        db.execute("INSERT INTO users VALUES (?, ?, ?)",
                   (payload.username, password_hash(payload.password), payload.role))
    return {"username": payload.username, "role": payload.role}
