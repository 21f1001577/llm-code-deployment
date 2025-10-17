import hashlib
import re
import base64


def hash_secret(s: str) -> str:
    """Return SHA256 hash of a given secret string."""
    return hashlib.sha256(s.encode()).hexdigest()


def decode_data_uri(uri: str):
    """Decode data URI (data:<mime>;base64,<content>)"""
    m = re.match(r"data:(.*?);base64,(.*)", uri)
    if not m:
        raise ValueError("Invalid data URI")
    mime = m.group(1)
    b64 = m.group(2)
    data = base64.b64decode(b64)
    return data, mime
