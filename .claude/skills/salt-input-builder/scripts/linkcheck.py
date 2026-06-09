"""Link liveness: every source_url must resolve before it ships.

Uses only the standard library so the skill stays portable. If the build
environment has no network egress, check_url returns (None, "no-network")
and the caller flags those links as 'liveness unverified' rather than
silently trusting or dropping them.

LIMITATION (be honest about this): a 2xx/3xx status confirms the server
responded, not that the URL is the intended page. Some sites answer missing
pages with a soft success (a 200 or 202 'soft-404') instead of a real 404, so
liveness can pass on a wrong-but-live URL. The primary defence is therefore the
rule never to construct or guess URLs: only ship links returned by a real
search or fetch, which were genuine at capture time. Liveness is a backstop,
and the human spot-check is the final one.
"""
from __future__ import annotations
import urllib.request, urllib.error, ssl, re

UA = "Mozilla/5.0 (compatible; salt-input-builder/1.0; link-liveness-check)"
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE  # liveness only, not a security check


_404_MARKERS = ("404", "not found", "page can't be found", "page cannot be found",
                "doesn't exist", "no longer available", "page not found")


def _looks_like_404(html):
    """Heuristic soft-404 detection: a 2xx page whose title or first H1 says 'not
    found'. Conservative - only the title/h1 zones, plus a strong phrase near the
    top - to avoid flagging real pages that merely mention 404 somewhere."""
    low = html.lower()
    zones = " ".join(
        m.group(1) for m in (
            re.search(r"<title[^>]*>(.*?)</title>", low, re.S),
            re.search(r"<h1[^>]*>(.*?)</h1>", low, re.S),
        ) if m
    )
    if zones and any(k in zones for k in _404_MARKERS):
        return True
    head = low[:2000]
    return "404 not found" in head or "page not found" in head


def check_url(url, timeout=14):
    """Return (ok: bool|None, detail: str). ok=None means could not determine.
    Does a GET and inspects the body so soft-404s (a 2xx for a missing page) are
    caught, not just hard error codes."""
    if not url or not url.startswith(("http://", "https://")):
        return False, "not-a-url"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            code = getattr(r, "status", r.getcode())
            body = r.read(6000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as ex:
        # 401/403/405/429 usually mean the page exists but blocks bots; treat as live.
        return (ex.code in (401, 403, 405, 429)), f"GET {ex.code}"
    except (urllib.error.URLError, TimeoutError, ssl.SSLError) as ex:
        reason = str(getattr(ex, "reason", ex))
        if "getaddrinfo" in reason or "Name or service not known" in reason:
            return None, "no-network"
        return None, f"unreachable: {reason[:60]}"
    except Exception as ex:  # noqa
        return None, f"error: {str(ex)[:60]}"
    if not (200 <= code < 400):
        return False, f"GET {code}"
    if _looks_like_404(body):
        return False, f"soft-404 ({code})"
    return True, f"GET {code}"


import urllib.parse

_PROBE_PATH = "/__liveness_probe_does_not_exist_zzz__/"


def _host(url):
    return urllib.parse.urlsplit(url).netloc


def check_many(urls, timeout=14):
    """Liveness-check a set of URLs, calibrated per host.

    Some hosts gate non-browser clients and return the SAME success response for
    a real page and a missing one (we saw a vendor return 202 for both). On such
    a host an HTTP check proves nothing, so asserting 'live' would be a false
    positive. For each host we first probe a deliberately-missing path: only if
    the host reports that probe as NOT live do we trust its per-URL results.
    Otherwise every URL on that host is reported (None, 'unverifiable...') and
    routed to the human to eyeball, which is the honest outcome."""
    out, reliable = {}, {}
    for u in dict.fromkeys(urls):
        h = _host(u)
        if h not in reliable:
            sp = urllib.parse.urlsplit(u)
            probe = f"{sp.scheme}://{h}{_PROBE_PATH}"
            pok, _ = check_url(probe, timeout)
            reliable[h] = (pok is False)  # trustworthy only if a missing path reads as dead
        out[u] = check_url(u, timeout) if reliable[h] else (None, "unverifiable: host gates bots / returns success for missing pages")
    return out


if __name__ == "__main__":
    import sys
    for u in sys.argv[1:]:
        print(u, "->", check_url(u))
