"""Meta Model API client for Kohu (Responses, Files, ASR, SAM).

One place for every call Kohu makes to Meta models:

  responses(body)              POST /v1/responses (Muse Spark, SAM 3.1)
  responses_background(body)   same with background=true, then polls
                               GET /v1/responses/{id} until it finishes
  upload_file(path)            POST /v1/files (purpose=user_data)
  transcribe(wav_path)         POST /v1/asr/transcribe (Muse Voice Transcribe)
  sam(image, prompt)           SAM 3.1 on one image, returns output_text

Behaviour shared by all calls:
  * Retry on 429 and 5xx (honours Retry-After), and on connection errors,
    with exponential backoff, at most MAX_ATTEMPTS attempts.
  * Usage log: every successful call appends one JSON line (endpoint,
    model, tokens or units, estimated USD) to META_USAGE_LOG
    (default logs/meta-usage.jsonl). The key and request bodies are never
    logged.
  * Spend stop: before each network call the logged spend is summed; at
    or above META_SPEND_LIMIT_USD (default 30) the call raises
    BudgetExceeded instead of spending more.
  * Cache: results are stored under corpus/spark-cache/ keyed by a hash of
    the request (file inputs hashed by content), so a seed or rerun reads
    the cache and never calls a model twice for the same input.
  * Transport is injectable, so tests replay recorded fixtures without
    network access.

Environment:
  META_API_KEY      bearer key (never printed)
  META_API_BASE     default https://api.meta.ai/v1
  META_PARSE_MODEL  default muse-spark-1.3
"""

import hashlib
import json
import mimetypes
import os
import pathlib
import random
import tempfile
import time
import urllib.error
import urllib.request
import uuid

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent

DEFAULT_BASE = "https://api.meta.ai/v1"
SPARK_MODEL = "muse-spark-1.3"
ASR_MODEL = "muse-voice-transcribe-1.0"
SAM_MODEL = "sam-3.1"

# Published prices (USD), dev.meta.ai pricing page as checked in G01.
PRICE_SPARK_INPUT_PER_M = 1.25
PRICE_SPARK_OUTPUT_PER_M = 4.25
PRICE_ASR_PER_HOUR = 0.18
PRICE_SAM_PER_IMAGE = 2.50 / 1000

MAX_ATTEMPTS = 4
# META_API_KEY=proxy-attached means an egress proxy adds the real key, so
# no Authorization header is sent from here.
PROXY_KEY = "proxy-attached"
DEFAULT_SPEND_LIMIT = 30.0
TERMINAL = {"completed", "failed", "cancelled", "incomplete"}


class MetaError(RuntimeError):
    """Any failed Meta API call after retries."""


class MetaUnavailable(MetaError):
    """No key configured, or the API host cannot be reached."""


class BudgetExceeded(MetaError):
    """Logged spend reached the configured stop."""


def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def estimate_cost(entry):
    """USD estimate for one usage log entry."""
    kind = entry.get("kind")
    if kind == "asr":
        return (entry.get("audio_seconds") or 0) / 3600.0 * PRICE_ASR_PER_HOUR
    if kind == "sam":
        return (entry.get("images") or 0) * PRICE_SAM_PER_IMAGE
    if kind == "spark":
        return ((entry.get("input_tokens") or 0) * PRICE_SPARK_INPUT_PER_M
                + (entry.get("output_tokens") or 0)
                * PRICE_SPARK_OUTPUT_PER_M) / 1e6
    return 0.0


def output_text(payload):
    """Concatenated output_text of a Responses payload ('' when none)."""
    if not isinstance(payload, dict):
        return ""
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    parts = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for part in item.get("content") or []:
                if (isinstance(part, dict)
                        and part.get("type") in ("output_text", "text")
                        and isinstance(part.get("text"), str)):
                    parts.append(part["text"])
        elif item.get("type") in ("output_text", "text") and isinstance(
                item.get("text"), str):
            parts.append(item["text"])
    return "".join(parts)


def output_json(payload):
    """Parse the output text as JSON (tolerates fenced code blocks)."""
    text = output_text(payload).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0],
                default=-1)
    if start > 0:
        text = text[start:]
    return json.loads(text)


def function_calls(payload):
    """[{call_id, name, arguments(dict)}] from a Responses payload."""
    calls = []
    for item in (payload or {}).get("output") or []:
        if isinstance(item, dict) and item.get("type") == "function_call":
            args = item.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except ValueError:
                    args = {"_unparsed": args}
            calls.append({"call_id": item.get("call_id") or item.get("id"),
                          "name": item.get("name"),
                          "arguments": args or {}})
    return calls


def _multipart(fields, files):
    """Encode multipart/form-data. files: {name: (filename, bytes, mime)}."""
    boundary = "kohu" + uuid.uuid4().hex
    out = []
    for name, value in fields.items():
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\""
                    "\r\n\r\n" % (boundary, name)).encode())
        out.append(value.encode() if isinstance(value, str) else value)
        out.append(b"\r\n")
    for name, (filename, data, mime) in files.items():
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; "
                    "filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                    % (boundary, name, filename, mime)).encode())
        out.append(data)
        out.append(b"\r\n")
    out.append(("--%s--\r\n" % boundary).encode())
    return b"".join(out), "multipart/form-data; boundary=" + boundary


class HttpResult:
    def __init__(self, status, body, headers=None):
        self.status = status
        self.body = body
        self.headers = headers or {}


def urllib_transport(method, url, data, headers, timeout):
    """Default transport. Returns HttpResult; raises OSError on no route."""
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResult(resp.status, resp.read(), dict(resp.headers))
    except urllib.error.HTTPError as e:
        return HttpResult(e.code, e.read(), dict(e.headers or {}))



TMP_CACHE = pathlib.Path(tempfile.gettempdir()) / "kohu-spark-cache"

class MetaClient:
    def __init__(self, key=None, base=None, model=None, transport=None,
                 cache_dir=None, usage_log=None, spend_limit=None,
                 use_cache=True, sleep=time.sleep):
        self.key = key if key is not None else os.environ.get("META_API_KEY")
        self.base = (base or os.environ.get("META_API_BASE")
                     or DEFAULT_BASE).rstrip("/")
        # Older .env files held the full /responses URL; accept both.
        if self.base.endswith("/responses"):
            self.base = self.base[:-len("/responses")]
        self.model = model or os.environ.get("META_PARSE_MODEL") or SPARK_MODEL
        self.transport = transport or urllib_transport
        self.cache_dir = pathlib.Path(
            cache_dir or os.environ.get("KOHU_SPARK_CACHE")
            or REPO / "corpus" / "spark-cache")
        self.usage_log = pathlib.Path(
            usage_log or os.environ.get("META_USAGE_LOG")
            or REPO / "logs" / "meta-usage.jsonl")
        self.spend_limit = (spend_limit if spend_limit is not None else
                            _env_float("META_SPEND_LIMIT_USD",
                                       DEFAULT_SPEND_LIMIT))
        self.use_cache = use_cache
        self.sleep = sleep
        self._down_until = 0.0
        self.calls = 0
        self.cache_hits = 0
        self.input_tokens = 0
        self.output_tokens = 0

    # ------------------------------------------------------------ state

    @property
    def enabled(self):
        return bool(self.key)

    @staticmethod
    def _db_usage():
        """Log usage in Postgres too when asked (public demo or env)."""
        return (os.environ.get("KOHU_USAGE_IN_DB") == "1"
                or os.environ.get("KOHU_PUBLIC_DEMO") == "1")

    def spent(self):
        """Total estimated USD: the database log when enabled, else the file."""
        if self._db_usage():
            try:
                import psycopg
                import db
                with psycopg.connect(db.database_url(), connect_timeout=5) as c:
                    row = c.execute("SELECT coalesce(sum(usd), 0) FROM "
                                    "meta_usage").fetchone()
                return float(row[0])
            except Exception:  # noqa: BLE001
                # Unknown spend must not mean unlimited spend.
                return float("inf")
        total = 0.0
        if self.usage_log.exists():
            for line in self.usage_log.read_text(encoding="utf-8").splitlines():
                try:
                    total += float(json.loads(line).get("usd", 0))
                except ValueError:
                    continue
        return total

    def _log_usage(self, entry):
        entry = dict(entry)
        entry["usd"] = round(estimate_cost(entry), 6)
        entry["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            self.usage_log.parent.mkdir(parents=True, exist_ok=True)
            with self.usage_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            # Read-only deploys (Vercel): the database log below still counts.
            pass
        if self._db_usage():
            try:
                import psycopg
                import db
                with psycopg.connect(db.database_url(), connect_timeout=5) as c:
                    c.execute(
                        "INSERT INTO meta_usage (kind, model, label, "
                        "input_tokens, output_tokens, audio_seconds, images, "
                        "usd) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (entry.get("kind"), entry.get("model"),
                         (entry.get("label") or "")[:120],
                         entry.get("input_tokens") or 0,
                         entry.get("output_tokens") or 0,
                         entry.get("audio_seconds") or 0,
                         entry.get("images") or 0, entry["usd"]))
            except Exception as e:  # noqa: BLE001
                print("warning: usage not logged to database: %s"
                      % type(e).__name__)
        self.input_tokens += entry.get("input_tokens") or 0
        self.output_tokens += entry.get("output_tokens") or 0

    # ------------------------------------------------------------ cache

    def cache_key(self, kind, body, file_digest=None):
        canon = json.dumps({"kind": kind, "body": body, "file": file_digest},
                           sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canon.encode()).hexdigest()[:32]

    def cache_get(self, key):
        if not self.use_cache:
            return None
        for d in (self.cache_dir, TMP_CACHE):
            path = d / (key + ".json")
            if path.exists():
                self.cache_hits += 1
                return json.loads(path.read_text(encoding="utf-8"))
        return None

    def cache_put(self, key, kind, value, label=None):
        if not self.use_cache:   # live-only runs neither read nor write it
            return
        rec = {"kind": kind, "label": label, "value": value,
               "cached_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        text = json.dumps(rec, indent=1)
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / (key + ".json")).write_text(text, encoding="utf-8")
        except OSError:
            # Read-only deploys (Vercel) can only write under /tmp.
            TMP_CACHE.mkdir(parents=True, exist_ok=True)
            (TMP_CACHE / (key + ".json")).write_text(text, encoding="utf-8")

    # ------------------------------------------------------------ http

    def _request(self, method, path, json_body=None, multipart=None,
                 timeout=120):
        if not self.enabled:
            raise MetaUnavailable("META_API_KEY is not set")
        if time.time() < self._down_until:
            raise MetaUnavailable("Meta API host unreachable (cooling down)")
        if self.spent() >= self.spend_limit:
            raise BudgetExceeded("logged spend %.2f USD reached the %.2f USD "
                                 "stop" % (self.spent(), self.spend_limit))
        headers = {"Accept": "application/json"}
        if self.key != PROXY_KEY:
            headers["Authorization"] = "Bearer " + self.key
        if multipart is not None:
            data, ctype = _multipart(*multipart)
            headers["Content-Type"] = ctype
        elif json_body is not None:
            data = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"
        else:
            data = None
        url = self.base + path
        last = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                res = self.transport(method, url, data, headers, timeout)
            except OSError as e:
                last = "connection error: %s" % type(e).__name__
                if attempt == MAX_ATTEMPTS - 1 or "403" in str(e):
                    # A proxy denial will not change on retry.
                    self._down_until = time.time() + 60
                    raise MetaUnavailable(
                        "Meta API host unreachable (%s)" % last) from None
                self.sleep(min(2 ** attempt, 8) + random.random() * 0.2)
                continue
            if res.status == 429 or res.status >= 500:
                last = "HTTP %d" % res.status
                if attempt == MAX_ATTEMPTS - 1:
                    break
                wait = res.headers.get("Retry-After") or res.headers.get(
                    "retry-after")
                try:
                    wait = float(wait)
                except (TypeError, ValueError):
                    wait = min(2 ** attempt, 8)
                self.sleep(wait + random.random() * 0.2)
                continue
            try:
                payload = json.loads(res.body.decode("utf-8") or "{}")
            except ValueError:
                payload = {"raw": res.body[:500].decode("utf-8", "replace")}
            if res.status >= 400:
                msg = payload.get("error") if isinstance(payload, dict) else None
                if isinstance(msg, dict):
                    msg = msg.get("message") or msg.get("type")
                raise MetaError("HTTP %d from %s: %s"
                                % (res.status, path, msg or "error"))
            self.calls += 1
            return payload
        raise MetaError("%s %s failed after %d attempts (%s)"
                        % (method, path, MAX_ATTEMPTS, last))

    def _spark_usage(self, payload, model, label):
        usage = (payload or {}).get("usage") or {}
        self._log_usage({
            "kind": "sam" if model == SAM_MODEL else "spark",
            "endpoint": "responses", "model": model, "label": label,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "images": 1 if model == SAM_MODEL else 0})

    # ------------------------------------------------------------ calls

    def responses(self, body, label=None, cache=True, file_digest=None):
        """POST /responses. Cached by request hash unless cache=False."""
        body = dict(body)
        body.setdefault("model", self.model)
        key = self.cache_key("responses", body, file_digest)
        if cache:
            hit = self.cache_get(key)
            if hit is not None:
                return hit["value"]
        payload = self._request("POST", "/responses", json_body=body)
        if payload.get("status") not in (None, "completed"):
            raise MetaError("response status %r" % payload.get("status"))
        self._spark_usage(payload, body["model"], label)
        if cache:
            self.cache_put(key, "responses", payload, label)
        return payload

    def responses_background(self, body, label=None, poll_interval=3.0,
                             timeout=900, cache=True, file_digest=None,
                             on_poll=None):
        """POST /responses with background=true, poll until terminal."""
        body = dict(body)
        body.setdefault("model", self.model)
        body["background"] = True
        key = self.cache_key("responses", body, file_digest)
        if cache:
            hit = self.cache_get(key)
            if hit is not None:
                return hit["value"]
        payload = self._request("POST", "/responses", json_body=body)
        rid = payload.get("id")
        started = time.time()
        while payload.get("status") not in TERMINAL:
            if time.time() - started > timeout:
                raise MetaError("background response %s timed out" % rid)
            self.sleep(poll_interval)
            payload = self._request("GET", "/responses/%s" % rid)
            if on_poll:
                on_poll(payload.get("status"))
        if payload.get("status") != "completed":
            raise MetaError("background response ended %r"
                            % payload.get("status"))
        self._spark_usage(payload, body["model"], label)
        if cache:
            self.cache_put(key, "responses", payload, label)
        return payload

    def upload_file(self, path, purpose="user_data", label=None):
        path = pathlib.Path(path)
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        key = self.cache_key("files", {"purpose": purpose}, digest)
        hit = self.cache_get(key)
        if hit is not None:
            return hit["value"]
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        payload = self._request(
            "POST", "/files", multipart=({"purpose": purpose},
                                         {"file": (path.name, data, mime)}),
            timeout=600)
        self._log_usage({"kind": "files", "endpoint": "files", "label": label,
                         "bytes": len(data)})
        self.cache_put(key, "files", payload, label)
        return payload

    def transcribe(self, wav_path, model=ASR_MODEL, label=None,
                   audio_seconds=None):
        """POST /asr/transcribe with a 16 kHz mono WAV (max 10 min, 32 MB)."""
        wav_path = pathlib.Path(wav_path)
        data = wav_path.read_bytes()
        if len(data) > 32 * 1024 * 1024:
            raise MetaError("audio exceeds 32 MB")
        request = {"model": model, "audioEncoding": "WAV",
                   "mode": "ENDPOINTING"}
        key = self.cache_key("asr", request, hashlib.sha256(data).hexdigest())
        hit = self.cache_get(key)
        if hit is not None:
            return hit["value"]
        payload = self._request(
            "POST", "/asr/transcribe",
            multipart=({"request": json.dumps(request)},
                       {"audio": (wav_path.name, data, "audio/wav")}),
            timeout=600)
        if audio_seconds is None:
            # 16-bit mono 16 kHz PCM after a 44-byte header.
            audio_seconds = max(0, len(data) - 44) / 32000.0
        self._log_usage({"kind": "asr", "endpoint": "asr/transcribe",
                         "model": model, "label": label,
                         "audio_seconds": audio_seconds})
        self.cache_put(key, "asr", payload, label)
        return payload

    def sam(self, image_bytes, prompt, mime="image/png", label=None,
            metadata=None):
        """SAM 3.1 on one image. Returns the raw output_text ('' = no match)."""
        import base64
        data_url = "data:%s;base64,%s" % (
            mime, base64.b64encode(image_bytes).decode())
        body = {"model": SAM_MODEL, "input": [{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": data_url}]}]}
        if metadata:
            body["metadata"] = metadata
        digest = hashlib.sha256(image_bytes).hexdigest()
        cache_body = {**body, "input": [{"prompt": prompt}]}
        key = self.cache_key("sam", cache_body, digest)
        hit = self.cache_get(key)
        if hit is not None:
            return output_text(hit["value"])
        payload = self._request("POST", "/responses", json_body=body)
        self._spark_usage(payload, SAM_MODEL, label)
        self.cache_put(key, "sam", payload, label)
        return output_text(payload)

    def list_models(self):
        return self._request("GET", "/models")


def ping(timeout=15):
    """(ok, detail) for GET /models; never prints the key."""
    client = MetaClient()
    if not client.enabled:
        # The cloud proxy may attach the key itself; try anyway.
        client.key = PROXY_KEY
    try:
        payload = client._request("GET", "/models", timeout=timeout)
        ids = sorted(m.get("id") for m in payload.get("data") or []
                     if isinstance(m, dict))
        return True, ids
    except MetaError as e:
        return False, str(e)


if __name__ == "__main__":
    ok, detail = ping()
    print("meta api:", "ok" if ok else "unreachable", detail)
    print("logged spend: %.4f USD" % MetaClient().spent())
