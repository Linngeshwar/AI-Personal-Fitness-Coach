"""
AES-GCM encryption for health fields (weight_kg, injuries, SafetyFlags)
before they touch the raw SQL INSERT. Not a library dependency -- a
12-line wrapper is all this needs.

Ciphertext layout stored in the BYTEA column: nonce (12 bytes) || ciphertext.
A fresh random nonce per encryption means the same plaintext never produces
the same ciphertext twice, so equality-based traffic analysis on the column
learns nothing.
"""
import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import load_dotenv

load_dotenv()

_NONCE_LEN = 12


def _key() -> bytes:
    raw = os.environ["HEALTH_ENCRYPTION_KEY"]
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise ValueError("HEALTH_ENCRYPTION_KEY must decode to 32 bytes (AES-256)")
    return key


def encrypt_health(data: dict) -> bytes:
    aesgcm = AESGCM(_key())
    nonce = os.urandom(_NONCE_LEN)
    plaintext = json.dumps(data).encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ciphertext


def decrypt_health(blob: bytes) -> dict:
    aesgcm = AESGCM(_key())
    nonce, ciphertext = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
    return json.loads(plaintext.decode("utf-8"))
