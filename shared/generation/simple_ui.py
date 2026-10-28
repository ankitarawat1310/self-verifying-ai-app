"""Optional end-user HTML for common generated workflow shapes."""

from __future__ import annotations

import json
import re
from pathlib import Path

_URL_SHORTENER_UI = '''
from fastapi.responses import HTMLResponse

_SVAGA_URL_SHORTENER_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>URL Shortener</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; max-width: 32rem; margin: 3rem auto; padding: 0 1rem; color: #1a1a1a; }
    h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
    p.sub { color: #555; margin-top: 0; margin-bottom: 1.5rem; }
    label { display: block; font-weight: 600; margin-bottom: 0.35rem; }
    input[type=url] { width: 100%; padding: 0.65rem 0.75rem; font-size: 1rem; border: 1px solid #ccc; border-radius: 6px; }
    button { margin-top: 1rem; width: 100%; padding: 0.75rem; font-size: 1rem; font-weight: 600; border: none; border-radius: 6px; background: #2563eb; color: #fff; cursor: pointer; }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    .result { margin-top: 1.5rem; padding: 1rem; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; display: none; }
    .result.error { background: #fef2f2; border-color: #fecaca; }
    .result a { word-break: break-all; color: #2563eb; }
    .copy { margin-top: 0.5rem; font-size: 0.875rem; color: #555; }
  </style>
</head>
<body>
  <h1>URL Shortener</h1>
  <p class="sub">Paste a long link and get a short one you can share.</p>
  <form id="f">
    <label for="url">Original URL</label>
    <input id="url" name="url" type="url" required placeholder="https://example.com/page" autocomplete="url" />
    <button type="submit" id="btn">Shorten</button>
  </form>
  <div id="out" class="result" role="status"></div>
  <script>
    const form = document.getElementById("f");
    const out = document.getElementById("out");
    const btn = document.getElementById("btn");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      btn.disabled = true;
      out.style.display = "none";
      out.classList.remove("error");
      const url = document.getElementById("url").value.trim();
      try {
        const res = await fetch("/shorten", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || "Could not shorten URL");
        const short = data.short_url || ("/r/" + data.code);
        const full = new URL(short, window.location.origin).href;
        out.innerHTML = "<strong>Short link</strong><br><a href=\"" + full + "\" id=\"link\">" + full + "</a><p class=\"copy\">Click the link to test, or copy it to share.</p>";
        out.style.display = "block";
      } catch (err) {
        out.textContent = err.message || "Something went wrong";
        out.classList.add("error");
        out.style.display = "block";
      } finally {
        btn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def _svaga_url_shortener_home():
    return HTMLResponse(_SVAGA_URL_SHORTENER_PAGE)
'''


def _is_url_shortener_spec(spec: dict) -> bool:
    if spec.get("workflow_id") == "url_shortener":
        return True
    paths = {e.get("path") for e in spec.get("endpoints") or [] if isinstance(e, dict)}
    return "/shorten" in paths and any(p and "/r/" in str(p) for p in paths)


def _strip_root_route(app_code: str) -> str:
    """Remove a simple @app.get(\"/\") handler so we can serve HTML at /."""
    pattern = (
        r"@app\.get\([\"']/[\"']\)\s*\n"
        r"def\s+\w+\([^)]*\):\s*\n"
        r"(?:[^\n]+\n)*?"
        r"(?=\n@app\.|\nclass\s|\Z)"
    )
    return re.sub(pattern, "\n", app_code, count=1)


def ensure_url_shortener_tests(test_code: str, spec: dict) -> str:
    if not _is_url_shortener_spec(spec):
        return test_code
    if "follow_redirects=False" in test_code:
        return test_code
    updated = test_code.replace(
        'got = client.get(f"/r/{code}")',
        'got = client.get(f"/r/{code}", follow_redirects=False)',
    )
    updated = updated.replace(
        'assert got.status_code == 200\n    assert got.json()["url"] == "https://example.com"',
        'assert got.status_code == 307\n    assert got.headers["location"] == "https://example.com"',
    )
    return updated


def ensure_url_shortener_ui(app_code: str, spec: dict) -> str:
    if not _is_url_shortener_spec(spec):
        return app_code
    if "_SVAGA_URL_SHORTENER_PAGE" in app_code:
        return app_code
    if "RedirectResponse" not in app_code and "@app.get(\"/r/" in app_code:
        fastapi_import = app_code.find("from fastapi import")
        if fastapi_import != -1:
            line_end = app_code.find("\n", fastapi_import)
            insert_at = line_end + 1 if line_end != -1 else len(app_code)
            app_code = (
                app_code[:insert_at]
                + "from fastapi.responses import RedirectResponse\n"
                + app_code[insert_at:]
            )
        else:
            app_code = "from fastapi.responses import RedirectResponse\n" + app_code
        app_code = re.sub(
            r"(@app\.get\(\"/r/\{code\}\"\)\s*\ndef redirect\([^)]*\):\s*\n"
            r"\s*if code not in _store:\s*\n"
            r"\s*raise HTTPException\(status_code=404, detail=\"not found\"\)\s*\n)"
            r"\s*return \{\"url\": _store\[code\]\}",
            r"\1    return RedirectResponse(_store[code], status_code=307)",
            app_code,
        )
    if 'short_url' not in app_code and "return {" in app_code and '"code"' in app_code:
        app_code = re.sub(
            r'return \{"code": code, "url": body\.url\}',
            'return {"code": code, "url": body.url, "short_url": f"/r/{code}"}',
            app_code,
            count=1,
        )
    app_code = _strip_root_route(app_code)
    return app_code.rstrip() + "\n" + _URL_SHORTENER_UI.strip() + "\n"


def finalize_generated_tests(test_code: str, spec: dict) -> str:
    return ensure_url_shortener_tests(test_code, spec)


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def ensure_generic_landing_ui(app_code: str, spec: dict) -> str:
    if _is_url_shortener_spec(spec) or "_SVAGA_LANDING_PAGE" in app_code:
        return app_code
    if '@app.get("/")' in app_code or "@app.get('/')" in app_code:
        return app_code
    from shared.generation.deploy_bundle import app_title

    title = _html_escape(app_title(spec))
    desc = _html_escape((spec.get("description") or "Use the API docs to work with this app.").strip())
    block = f'''
from fastapi.responses import HTMLResponse

_SVAGA_LANDING_PAGE = """
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:36rem;margin:3rem auto;padding:0 1rem;color:#1a1a1a}}
h1{{font-size:1.5rem}}p{{color:#444;line-height:1.5}}a.btn{{display:inline-block;margin-top:1rem;padding:.65rem 1rem;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:600}}</style>
</head><body><h1>{title}</h1><p>{desc}</p><a class="btn" href="/docs">Open API docs</a></body></html>
"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def _svaga_landing():
    return HTMLResponse(_SVAGA_LANDING_PAGE)
'''
    if "from fastapi.responses import HTMLResponse" not in app_code:
        fastapi_import = app_code.find("from fastapi import")
        if fastapi_import != -1:
            line_end = app_code.find("\n", fastapi_import)
            insert_at = line_end + 1 if line_end != -1 else len(app_code)
            app_code = app_code[:insert_at] + "from fastapi.responses import HTMLResponse\n" + app_code[insert_at:]
    return app_code.rstrip() + "\n" + block.strip() + "\n"


_UI_MARKER = "_SVAGA_UI_PAGE"
_UI_TEMPLATE = Path(__file__).with_name("app_ui.html")


def ui_config(spec: dict) -> dict:
    """What the generic app UI needs from the spec: a title, one line of description, roles and route summaries."""
    from shared.generation.deploy_bundle import app_title

    desc = (spec.get("description") or "").split("Public interface", 1)[0].strip()
    roles = [a.get("id") for a in spec.get("actors") or [] if isinstance(a, dict) and a.get("id")]
    endpoints = [
        {"method": str(e.get("method", "GET")).upper(), "path": e.get("path", ""),
         "summary": e.get("business_action") or "", "roles": list(e.get("allowed_roles") or [])}
        for e in spec.get("endpoints") or [] if isinstance(e, dict)
    ]
    return {"title": app_title(spec), "description": desc[:600], "roles": roles, "endpoints": endpoints}


def ui_block(spec: dict) -> str:
    """Python code that serves a working web UI for this app at /ui (and at / when the app has no / of its own).

    The page reads the app's own /openapi.json and builds a form for every route, an identity bar for header-based
    roles, and a live table of records, so it works for any generated app without the LLM writing any UI code.
    Routes are added at runtime only if missing, so the block is safe to append to any app, more than once.
    """
    page = _UI_TEMPLATE.read_text(encoding="utf-8").replace(
        "/*__SVAGA_CONFIG__*/null", json.dumps(ui_config(spec)).replace("</", "<\\/"))
    return (
        "\n\n# --- SVAGA app UI: a form for every route, built from this app's own API description ---\n"
        "from fastapi.responses import HTMLResponse as _SvagaHTMLResponse\n"
        f"{_UI_MARKER} = {page!r}\n\n\n"
        "def _svaga_ui():\n"
        f"    return _SvagaHTMLResponse({_UI_MARKER})\n\n\n"
        '_svaga_paths = {getattr(_r, "path", None) for _r in app.routes}\n'
        'if "/ui" not in _svaga_paths:\n'
        '    app.add_api_route("/ui", _svaga_ui, methods=["GET"], include_in_schema=False, response_class=_SvagaHTMLResponse)\n'
        'if "/" not in _svaga_paths:\n'
        '    app.add_api_route("/", _svaga_ui, methods=["GET"], include_in_schema=False, response_class=_SvagaHTMLResponse)\n'
    )


def _strip_platform_roots(app_code: str) -> str:
    """Remove the platform's own placeholder / routes (JSON welcome, old landing page) so the UI can take /."""
    app_code = re.sub(r'\n*@app\.get\("/"\)\ndef _svaga_root\(\):\n    return \{[^\n]*\}\n', "\n", app_code)
    if "_SVAGA_LANDING_PAGE" in app_code:
        app_code = re.sub(r'\n*from fastapi\.responses import HTMLResponse\n\n_SVAGA_LANDING_PAGE = """.*?"""\n+'
                          r'@app\.get\("/", response_class=HTMLResponse, include_in_schema=False\)\n'
                          r'def _svaga_landing\(\):\n    return HTMLResponse\(_SVAGA_LANDING_PAGE\)\n?', "\n", app_code, flags=re.S)
    return app_code


def ensure_app_ui(app_code: str, spec: dict) -> str:
    if _UI_MARKER in app_code or "FastAPI" not in app_code or not app_code.strip():
        return app_code
    return _strip_platform_roots(app_code).rstrip() + "\n" + ui_block(spec)


def finalize_generated_app(app_code: str, spec: dict) -> str:
    from shared.generation.app_bootstrap import ensure_fastapi_health_route, ensure_fastapi_welcome_routes

    app_code = ensure_url_shortener_ui(app_code, spec)
    if _is_url_shortener_spec(spec):
        return ensure_fastapi_health_route(app_code)
    app_code = ensure_app_ui(app_code, spec)
    return ensure_fastapi_welcome_routes(app_code)
