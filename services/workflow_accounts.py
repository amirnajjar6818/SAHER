"""Visible account references, never biometric identity or inferred personal traits."""
import re

PLATFORMS = {"instagram", "telegram", "x", "tiktok", "youtube", "facebook", "unknown"}
URLS = (
    ("instagram", r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9_.]{1,80})"),
    ("telegram", r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([A-Za-z0-9_]{1,80})"),
    ("x", r"(?:https?://)?(?:www\.)?(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,80})"),
    ("tiktok", r"(?:https?://)?(?:www\.)?tiktok\.com/@([A-Za-z0-9_.]{1,80})"),
    ("youtube", r"(?:https?://)?(?:www\.)?youtube\.com/@([A-Za-z0-9_.-]{1,80})"),
    ("facebook", r"(?:https?://)?(?:www\.)?facebook\.com/([A-Za-z0-9_.]{1,80})"),
)
RESERVED = {"p", "reel", "reels", "stories", "explore", "share", "watch", "shorts", "home", "search", "intent", "status", "i"}


def candidates(text):
    """Candidates are mentions in content, not proof of authorship or identity."""
    result = []
    seen = set()
    for platform, pattern in URLS:
        for match in re.finditer(r"(?<![A-Za-z0-9_.-])" + pattern, text, re.I):
            handle = match.group(1)
            key = (platform, handle.lower())
            if handle.lower() not in RESERVED and key not in seen:
                result.append({"platform": platform, "handle": handle, "evidence": match.group(0), "basis": "visible_url"})
                seen.add(key)
    known = {item["handle"].lower() for item in result}
    for match in re.finditer(r"(?<![\w@.+-])@([A-Za-z0-9_][A-Za-z0-9_.-]{0,79})(?![A-Za-z0-9_.-])", text):
        handle = match.group(1).rstrip(".-")
        key = ("unknown", handle.lower())
        if handle.lower() not in known and key not in seen:
            result.append({"platform": "unknown", "handle": handle, "evidence": match.group(0), "basis": "visible_mention"})
            seen.add(key)
    return result[:100]


def initialize(db):
    db.execute("CREATE TABLE IF NOT EXISTS image_accounts (id TEXT PRIMARY KEY, scope TEXT NOT NULL, platform TEXT NOT NULL, handle TEXT NOT NULL, UNIQUE(scope, platform, handle))")
