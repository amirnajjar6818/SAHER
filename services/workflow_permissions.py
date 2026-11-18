"""Case memberships and private ownership of unassigned workflow records."""
from fastapi import HTTPException


def initialize(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS case_members ("
        "case_id TEXT NOT NULL, username TEXT NOT NULL, permission TEXT NOT NULL, "
        "PRIMARY KEY (case_id, username))"
    )


def case_allowed(db, user, case_id, write=False):
    if user["role"] == "admin":
        return True
    row = db.execute(
        "SELECT permission FROM case_members WHERE case_id=? AND username=?",
        (case_id, user["username"]),
    ).fetchone()
    return row is not None and (not write or row["permission"] == "editor")


def record_allowed(db, user, record, write=False):
    if user["role"] == "admin":
        return True
    if record.get("case_id"):
        return case_allowed(db, user, record["case_id"], write)
    return record.get("owner") == user["username"]


def require_record(db, user, record, write=False):
    if not record_allowed(db, user, record, write):
        raise HTTPException(404, "محتوا یافت نشد")


def require_case(db, user, case_id, write=False):
    if not case_allowed(db, user, case_id, write):
        raise HTTPException(404, "پرونده یا رویداد یافت نشد")
