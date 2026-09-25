"""
chain/crypto.py — Hashing, canonical JSON and Ed25519 signing keys.

Keys are generated on first use and stored as PEM files:
  chain_data/<node>/node.key       one per agency node (endorsements)
  chain_data/keystore/<actor>.key  one per officer / service (entry signatures)
"""

from __future__ import annotations

import hashlib
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (Ed25519PrivateKey,
                                                               Ed25519PublicKey)

from app.chain import DATA_DIR, NODES


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _key_path(name: str):
    return DATA_DIR / name / "node.key" if name in NODES else DATA_DIR / "keystore" / f"{name}.key"


_CACHE: dict[str, tuple[int, Ed25519PrivateKey]] = {}


def private_key(name: str) -> Ed25519PrivateKey:
    """Load (or create) a key; the cache follows the file, so a fresh chain gets fresh keys."""
    path = _key_path(name)
    if not path.exists():
        key = Ed25519PrivateKey.generate()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                           serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    stamp = path.stat().st_mtime_ns
    if name not in _CACHE or _CACHE[name][0] != stamp:
        _CACHE[name] = (stamp, serialization.load_pem_private_key(path.read_bytes(), password=None))
    return _CACHE[name][1]


def public_hex(name: str) -> str:
    return private_key(name).public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def sign(name: str, message: str) -> str:
    return private_key(name).sign(message.encode("utf-8")).hex()


def verify(pub_hex: str, message: str, sig_hex: str) -> bool:
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex)).verify(
            bytes.fromhex(sig_hex), message.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError):
        return False


def fingerprint(pub_hex: str) -> str:
    return sha256(pub_hex)[:16]


def reset_cache() -> None:
    _CACHE.clear()
