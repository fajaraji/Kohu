"""Public demo mode (KOHU_PUBLIC_DEMO=1).

A public URL lets anyone pick any persona, including Steward and Manager.
In public demo mode:
  * Steward decisions are stored per visitor (visitor_decisions), so a
    visitor sees the effect of their own decision and nobody else's.
    Each browser gets a random visitor id at login; it is carried in the
    signed token. POST /demo/reset clears that visitor's decisions.
  * Video upload and step editing are off (they would change shared data
    and spend Meta credits).
  * Asks are rate limited per visitor, per client IP and globally.
  * Meta usage is logged to the database (see meta_client), so the spend
    stop survives restarts.

Endpoints set the visitor for the current request with visitor_scope();
conflict functions read it with current_visitor().
"""

import collections
import contextlib
import contextvars
import os
import threading
import time

_visitor = contextvars.ContextVar("kohu_visitor", default=None)


def public():
    return os.environ.get("KOHU_PUBLIC_DEMO") == "1"


@contextlib.contextmanager
def visitor_scope(visitor):
    token = _visitor.set(visitor if public() else None)
    try:
        yield
    finally:
        _visitor.reset(token)


def current_visitor():
    return _visitor.get() if public() else None


def _parse(spec, default):
    try:
        n, window = (os.environ.get(spec) or default).split("/")
        return int(n), float(window)
    except ValueError:
        n, window = default.split("/")
        return int(n), float(window)


class RateLimiter:
    """Sliding window limits; in memory, one process (uvicorn default)."""

    def __init__(self):
        self._hits = collections.defaultdict(collections.deque)
        self._lock = threading.Lock()

    def check(self, keys, now=None):
        """keys: [(name, key, limit_env, default)]. Returns a message or None.

        Records the hit only when every limit allows it.
        """
        now = now or time.time()
        with self._lock:
            for name, key, env, default in keys:
                limit, window = _parse(env, default)
                q = self._hits[(name, key)]
                while q and q[0] <= now - window:
                    q.popleft()
                if len(q) >= limit:
                    wait = int(q[0] + window - now) + 1
                    return ("The public demo allows %d questions per %s. "
                            "Try again in %d s." % (
                                limit, _human(window), wait))
            for name, key, _env, _default in keys:
                self._hits[(name, key)].append(now)
        return None


def _human(seconds):
    if seconds >= 3600:
        return "%d hour%s" % (seconds // 3600, "s" if seconds >= 7200 else "")
    return "%d minutes" % (seconds // 60)


ask_limiter = RateLimiter()
ASK_LIMITS = (("visitor", "KOHU_ASK_LIMIT_VISITOR", "16/600"),
              ("ip", "KOHU_ASK_LIMIT_IP", "60/3600"),
              ("global", "KOHU_ASK_LIMIT_GLOBAL", "400/3600"))


def check_ask(visitor, ip, cost=1):
    if not public():
        return None
    keys = [(name, {"visitor": visitor, "ip": ip, "global": "*"}[name],
             env, default) for name, env, default in ASK_LIMITS]
    for _ in range(cost):
        msg = ask_limiter.check(keys)
        if msg:
            return msg
    return None
