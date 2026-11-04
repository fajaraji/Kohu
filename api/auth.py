"""Signed persona tokens (demo login, no identity provider).

POST /login {persona, user?} returns a token = base64url(payload) + "." +
HMAC-SHA256(payload, KOHU_SESSION_SECRET). Every route reads the persona
from a verified token, never from the request body or query, so a user
cannot widen access by editing a field.

If KOHU_SESSION_SECRET is unset a random per-process secret is used and
tokens stop working after a restart (fine for local runs, logged once).
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time

import policy

TOKEN_TTL_S = 12 * 3600
_fallback_secret = None


def _secret():
    global _fallback_secret
    s = os.environ.get("KOHU_SESSION_SECRET")
    if s:
        return s.encode()
    if _fallback_secret is None:
        _fallback_secret = secrets.token_bytes(32)
        print("warning: KOHU_SESSION_SECRET unset; using a per-process "
              "secret", file=sys.stderr)
    return _fallback_secret


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class AuthError(Exception):
    pass


def new_visitor():
    return secrets.token_hex(8)


def issue(persona, user=None, now=None, visitor=None):
    """Signed token. visitor groups the tokens of one browser (demo mode)."""
    policy.check_persona(persona)
    visitor = visitor if re.fullmatch(r"[a-f0-9]{8,32}", visitor or "") \
        else new_visitor()
    user = user or "demo-" + persona
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,64}", user):
        raise ValueError("user must be 1-64 letters, digits or _.@-")
    now = int(now or time.time())
    payload = _b64(json.dumps({"p": persona, "u": user, "v": visitor,
                               "iat": now, "exp": now + TOKEN_TTL_S},
                              separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return payload + "." + sig


def verify(token, now=None):
    """{"persona", "user"} for a valid token, else AuthError."""
    if not token or "." not in token:
        raise AuthError("missing or malformed token")
    payload, sig = token.rsplit(".", 1)
    want = _b64(hmac.new(_secret(), payload.encode(),
                         hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig):
        raise AuthError("bad token signature")
    try:
        data = json.loads(_unb64(payload))
    except ValueError:
        raise AuthError("malformed token") from None
    if data.get("exp", 0) < (now or time.time()):
        raise AuthError("token expired")
    if data.get("p") not in policy.PERSONAS:
        raise AuthError("unknown persona in token")
    return {"persona": data["p"], "user": data.get("u") or data["p"],
            "visitor": data.get("v") or "none"}
