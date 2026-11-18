"""Stream file bytes to ClamAV without sharing the archive filesystem."""
import hashlib
import os
import socket
import struct
from datetime import datetime, timezone


def read_reply(connection):
    response = bytearray()
    while len(response) < 8192:
        chunk = connection.recv(1024)
        if not chunk:
            break
        response.extend(chunk)
        if b"\0" in chunk or b"\n" in chunk:
            break
    return response.decode("utf-8", errors="replace").strip("\0\r\n")


def scan_file(path):
    result = {"status": "unavailable", "checked_at": datetime.now(timezone.utc).isoformat(),
              "engine": "ClamAV", "signature": "", "sha256": ""}
    digest = hashlib.sha256()
    address = (os.environ.get("SAHER_CLAMD_HOST", "antivirus"),
               int(os.environ.get("SAHER_CLAMD_PORT", "3310")))
    try:
        with socket.create_connection(address, timeout=10) as connection:
            connection.settimeout(90)
            connection.sendall(b"zINSTREAM\0")
            with path.open("rb") as original:
                while chunk := original.read(65536):
                    digest.update(chunk)
                    connection.sendall(struct.pack("!I", len(chunk)) + chunk)
            connection.sendall(struct.pack("!I", 0))
            reply = read_reply(connection)
        result["sha256"] = digest.hexdigest()
        if reply == "stream: OK":
            result["status"] = "clean"
        elif reply.startswith("stream: ") and reply.endswith(" FOUND"):
            result["status"] = "infected"
            result["signature"] = reply[len("stream: "):-len(" FOUND")]
        else:
            result["detail"] = "اسکن کامل نشد؛ فایل در قرنطینه باقی می‌ماند"
        with socket.create_connection(address, timeout=10) as connection:
            connection.sendall(b"zVERSION\0")
            result["engine"] = read_reply(connection)
    except (OSError, ValueError):
        result["status"] = "unavailable"
        result["detail"] = "اسکنر در دسترس نیست؛ اسکن را دوباره اجرا کنید"
    return result


def require_clean(record, path):
    from fastapi import HTTPException
    scan = record.get("antivirus", {})
    if scan.get("status") != "clean":
        raise HTTPException(423, "فایل تا دریافت نتیجهٔ سالم ضدبدافزار در قرنطینه است")
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise HTTPException(404, "اصل فایل یافت نشد")
    if digest != scan.get("sha256") or digest != record.get("sha256"):
        raise HTTPException(423, "اصل فایل تغییر کرده است؛ اسکن مجدد لازم است")
