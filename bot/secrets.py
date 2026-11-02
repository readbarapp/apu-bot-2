from __future__ import annotations

import hmac
import json
import os
import re
import secrets as pysecrets
from hashlib import pbkdf2_hmac
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
SECRETS_DIR = ROOT / "secrets"
KEY_NAME = "BOT_SECRETS_KEY"

_MASKED_CARD = re.compile(r"^•+\s*\d{2,4}$")


def _load_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _write_env_key(key_hex: str) -> None:
    existing = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    lines = [line for line in existing.splitlines() if not line.startswith(f"{KEY_NAME}=")]
    lines.append(f"{KEY_NAME}={key_hex}")
    ENV_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def secrets_key() -> bytes:
    env = _load_env_file()
    raw = os.environ.get(KEY_NAME) or env.get(KEY_NAME) or ""
    if not raw:
        raw = pysecrets.token_hex(32)
        os.environ[KEY_NAME] = raw
        _write_env_key(raw)
    return bytes.fromhex(raw) if re.fullmatch(r"[0-9a-fA-F]+", raw) and len(raw) >= 32 else raw.encode("utf-8")


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(byte ^ key[index % len(key)] for index, byte in enumerate(data))


def encrypt_text(plain: str) -> str:
    nonce = os.urandom(16)
    derived = pbkdf2_hmac("sha256", secrets_key(), nonce, 120_000, 32)
    mixed = _xor(plain.encode("utf-8"), derived)
    digest = hmac.new(derived, nonce + mixed, "sha256").digest()
    return (nonce + digest + mixed).hex()


def decrypt_text(blob: str) -> str:
    raw = bytes.fromhex(blob)
    nonce, digest, mixed = raw[:16], raw[16:48], raw[48:]
    derived = pbkdf2_hmac("sha256", secrets_key(), nonce, 120_000, 32)
    if not hmac.compare_digest(digest, hmac.new(derived, nonce + mixed, "sha256").digest()):
        raise ValueError("guest secrets file is corrupt or the key does not match")
    return _xor(mixed, derived).decode("utf-8")


def is_masked_card(value: str | None) -> bool:
    text = (value or "").strip()
    return not text or bool(_MASKED_CARD.match(text))


def public_guest(guest: dict) -> dict:
    digits = re.sub(r"\D", "", str(guest.get("card_number") or ""))
    return {
        "last_name": guest.get("last_name") or "",
        "first_name": guest.get("first_name") or "",
        "email": guest.get("email") or "",
        "phone": guest.get("phone") or "",
        "address": guest.get("address") or "",
        "card_number": f"•••• {digits[-4:]}" if len(digits) >= 4 else "",
        "card_month": guest.get("card_month") or "",
        "card_year": guest.get("card_year") or "",
        "cvv": "",
    }


def save_guest_secrets(worker_id: str, guest: dict) -> None:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_name": guest.get("last_name") or "",
        "first_name": guest.get("first_name") or "",
        "email": guest.get("email") or "",
        "phone": guest.get("phone") or "",
        "address": guest.get("address") or "",
        "card_number": re.sub(r"\D", "", str(guest.get("card_number") or "")),
        "card_month": guest.get("card_month") or "",
        "card_year": guest.get("card_year") or "",
        "cvv": str(guest.get("cvv") or "").strip(),
    }
    path = SECRETS_DIR / f"{worker_id}.enc"
    path.write_text(encrypt_text(json.dumps(payload, ensure_ascii=False)), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_guest_secrets(worker_id: str) -> dict | None:
    path = SECRETS_DIR / f"{worker_id}.enc"
    if not path.exists():
        return None
    return json.loads(decrypt_text(path.read_text(encoding="utf-8")))


def merge_guest_payload(worker_id: str, incoming: dict) -> dict:
    stored = load_guest_secrets(worker_id) or {}
    merged = {**stored}
    for key, value in incoming.items():
        text = str(value or "").strip()
        if key == "card_number" and (is_masked_card(text) or not text):
            continue
        if key == "cvv" and not text:
            continue
        if text:
            merged[key] = text
    if merged.get("card_number") and merged.get("cvv"):
        save_guest_secrets(worker_id, merged)
    return merged
