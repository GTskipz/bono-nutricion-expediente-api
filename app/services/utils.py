from __future__ import annotations

from datetime import datetime, date
import hashlib
import re
import unicodedata


def norm_str(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s != "" else None


def to_int(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return int(float(v))
    except Exception:
        return None


def to_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def to_cui(v):
    if v is None:
        return None
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        try:
            return str(int(v))
        except Exception:
            return norm_str(v)
    s = str(v).strip()
    if s == "":
        return None
    if re.fullmatch(r"\d+\.0+", s):
        return s.split(".")[0]
    return s


def to_rub(v):
    if v is None:
        return None

    if isinstance(v, int):
        return str(v)

    if isinstance(v, float):
        try:
            return str(int(v))
        except Exception:
            s = str(v).strip()
            return s if s != "" else None

    s = str(v).strip()
    if s == "":
        return None
    if re.fullmatch(r"\d+\.0+", s):
        return s.split(".")[0]
    return s


def norm_lookup(s: str | None) -> str | None:
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    s = s.upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip()
    return s
