"""Browser runtime service split from server.py."""

import sys

__all__ = ['_browser_viewer_probe', '_browser_viewer_upstream_parts', '_browser_viewer_password', '_handle_browser_controller', '_handle_browser_status', '_handle_browser_viewer_status', '_handle_browser_tabs']


def _server_module():
    return sys.modules.get("server") or sys.modules.get("__main__")


def _hydrate():
    server = _server_module()
    if server is None or server is sys.modules.get(__name__):
        return
    exported = set(__all__)
    for key, value in vars(server).items():
        if key.startswith("__") or key in ("_server_module", "_hydrate", "_wrap_exports"):
            continue
        if key in exported and callable(value) and (
            getattr(value, "_service_wrapper", False) or getattr(value, "_service_wrapped", False)
        ):
            continue
        globals()[key] = value


def _wrap_exports():
    current = sys.modules[__name__]
    for name in __all__:
        value = globals().get(name)
        if not callable(value) or getattr(value, "_service_wrapped", False):
            continue

        def make_wrapper(fn):
            def wrapper(*args, **kwargs):
                _hydrate()
                return fn(*args, **kwargs)
            wrapper.__name__ = fn.__name__
            wrapper.__doc__ = fn.__doc__
            wrapper.__dict__.update(getattr(fn, "__dict__", {}))
            wrapper._service_wrapped = True
            return wrapper

        setattr(current, name, make_wrapper(value))


def _browser_viewer_probe(viewer_url):
    if not viewer_url:
        return {"ok": False, "error": "Viewer URL is not configured"}
    try:
        parsed = urllib.parse.urlparse(viewer_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return {"ok": False, "error": "Viewer URL must be http(s)"}

        path = parsed.path or "/"
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if "path" not in query:
            base_path = path.strip("/")
            query["path"] = [(base_path + "/" if base_path else "") + "websockify"]
        query.setdefault("resize", ["scale"])
        query.setdefault("autoconnect", ["1"])

        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = "[" + host + "]"
        if parsed.port:
            host = f"{host}:{parsed.port}"
        probe_url = urllib.parse.urlunparse((
            parsed.scheme,
            host,
            path,
            "",
            urllib.parse.urlencode(query, doseq=True),
            "",
        ))
        headers = {"User-Agent": "VirtualOffice/1.0"}
        if parsed.username is not None:
            username = urllib.parse.unquote(parsed.username or "")
            password = urllib.parse.unquote(parsed.password or "")
            token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = "Basic " + token
        req = urllib.request.Request(probe_url, headers=headers, method="GET")
        context = ssl._create_unverified_context() if parsed.scheme == "https" else None
        with urllib.request.urlopen(req, timeout=4, context=context) as resp:
            return {"ok": 200 <= resp.status < 400, "status": resp.status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _browser_viewer_upstream_parts():
    viewer_url = VO_CONFIG.get("browser", {}).get("viewerUrl")
    if not viewer_url:
        return None, None
    parsed = urllib.parse.urlparse(viewer_url)
    headers = {"User-Agent": "VirtualOffice/1.0"}
    if parsed.username is not None:
        username = urllib.parse.unquote(parsed.username or "")
        password = urllib.parse.unquote(parsed.password or "")
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic " + token
    clean_netloc = parsed.hostname or ""
    if ":" in clean_netloc and not clean_netloc.startswith("["):
        clean_netloc = "[" + clean_netloc + "]"
    if parsed.port:
        clean_netloc = f"{clean_netloc}:{parsed.port}"
    clean_base = urllib.parse.urlunparse((parsed.scheme, clean_netloc, "", "", "", ""))
    return clean_base.rstrip("/"), headers


def _browser_viewer_password():
    viewer_url = VO_CONFIG.get("browser", {}).get("viewerUrl") or ""
    parsed = urllib.parse.urlparse(viewer_url)
    return urllib.parse.unquote(parsed.password or "")




def _handle_browser_controller():
    try:
        with open(os.path.join(STATUS_DIR, "browser-controller.json"), "r") as f:
            data = json.loads(f.read())
        if time.time() - data.get("ts", 0) > 120:
            data = {"agent": None}
        return data
    except Exception:
        return {"agent": None}


def _handle_browser_status():
    enabled = VO_CONFIG.get("features", {}).get("browserPanel", False) and check_feature("browserPanel")
    cdp_url = VO_CONFIG.get("browser", {}).get("cdpUrl")
    viewer_url = VO_CONFIG.get("browser", {}).get("viewerUrl")
    cdp_available = False
    if enabled and cdp_url:
        try:
            urllib.request.urlopen(cdp_url.rstrip("/") + "/json", timeout=2)
            cdp_available = True
        except Exception:
            pass
    return {"enabled": enabled, "cdpAvailable": cdp_available, "viewerUrl": viewer_url, "cdpUrl": cdp_url}


def _handle_browser_viewer_status():
    return _browser_viewer_probe(VO_CONFIG.get("browser", {}).get("viewerUrl"))


def _handle_browser_tabs():
    cdp_url = VO_CONFIG.get("browser", {}).get("cdpUrl")
    if not cdp_url:
        return {"available": False}
    try:
        req = urllib.request.urlopen(cdp_url.rstrip("/") + "/json", timeout=2)
        return json.loads(req.read().decode())
    except Exception as e:
        return {"available": False, "error": str(e)}

_wrap_exports()
_hydrate()
