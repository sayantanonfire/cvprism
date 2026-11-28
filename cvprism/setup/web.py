"""Browser-based first-run wizard (M6). Serves one form on 127.0.0.1, guarded by a one-time token
and a Host-header check (DNS-rebinding defence). Calls the same `configure()` as the TUI."""
from __future__ import annotations

import html
import secrets
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import wizard

CSS = """
:root{--paper:#EEF1F5;--ink:#1A2230;--muted:#5A6577;--line:#CDD3DC;--act:#3346C8;--err:#B3261E;--field:#FFFFFF}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.spectrum{height:6px;background:linear-gradient(90deg,#3346C8 0 20%,#2A9D8F 20% 40%,#E9C46A 40% 60%,#F4A261 60% 80%,#E5533D 80%)}
main{max-width:620px;margin:0 auto;padding:40px 24px 64px}
h1{font-size:28px;line-height:1.2;margin:0 0 6px;font-weight:650;letter-spacing:-.01em}
.lede{color:var(--muted);margin:0 0 32px;max-width:60ch}
fieldset{border:0;border-top:1px solid var(--line);margin:0;padding:22px 0 8px}
legend{font-size:17px;font-weight:600;padding:0 0 10px}
label{display:block;font-weight:550;margin:14px 0 4px}
.hint{display:block;color:var(--muted);font-weight:400;font-size:13.5px;margin-top:2px}
input[type=text]{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:6px;background:var(--field);font:inherit;color:inherit}
input[type=text]:focus-visible,button:focus-visible,.tile:focus-within{outline:3px solid #9AA8F0;outline-offset:2px}
.tiles{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:4px}
.tile{display:block;border:1px solid var(--line);border-radius:8px;padding:12px 14px;background:var(--field);cursor:pointer;margin:0;font-weight:400}
.tile input{margin-right:8px}
.tile b{font-weight:600}
.tile span{display:block;color:var(--muted);font-size:13.5px;margin-top:4px}
.tile:has(input:checked){border-color:var(--act);box-shadow:inset 0 0 0 1px var(--act)}
.check{display:flex;gap:8px;align-items:flex-start;font-weight:400}
button{margin-top:28px;background:var(--act);color:#fff;border:0;border-radius:6px;padding:11px 18px;font:inherit;font-weight:600;cursor:pointer}
.error{border-left:4px solid var(--err);background:#FBEAE9;padding:10px 14px;margin:0 0 24px;border-radius:0 6px 6px 0}
.done code,.done pre{background:var(--field);border:1px solid var(--line);border-radius:6px}
.done pre{padding:12px 14px;overflow-x:auto}
@media (max-width:560px){.tiles{grid-template-columns:1fr}}
"""


def _page(body: str, title: str = "Set up cvprism") -> bytes:
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{title}</title>"
            f"<style>{CSS}</style></head><body><div class='spectrum' aria-hidden='true'></div>"
            f"<main>{body}</main></body></html>").encode("utf-8")


def form_html(token: str, values: dict | None = None, error: str | None = None) -> bytes:
    v = {k: html.escape(str(x)) for k, x in (values or {}).items()}
    role = (values or {}).get("role", "hub")
    err = f"<p class='error' role='alert'>{html.escape(error)}</p>" if error else ""
    checked = "" if values is not None and not (values or {}).get("claude") else "checked"
    default_vault = html.escape(str(wizard.default_vault_path()))
    return _page(f"""
<h1>Set up cvprism on this computer</h1>
<p class="lede">cvprism records the skills and results in your everyday work, and turns them into CVs where every line points to evidence. This takes about a minute. You can change any answer later.</p>
{err}
<form method="post" action="/setup">
<input type="hidden" name="token" value="{html.escape(token)}">
<fieldset><legend>This computer</legend>
<label for="name">Device name<span class="hint">Shown in sync logs, e.g. office-laptop.</span></label>
<input type="text" id="name" name="name" required value="{v.get('name', '')}">
</fieldset>
<fieldset><legend>Its role</legend>
<div class="tiles" role="radiogroup">
<label class="tile"><input type="radio" name="role" value="hub" {'checked' if role == 'hub' else ''}><b>Hub</b>
<span>Your main computer. It keeps the vault and builds your CVs. Choose this on your first computer.</span></label>
<label class="tile"><input type="radio" name="role" value="spoke" {'checked' if role == 'spoke' else ''}><b>Spoke</b>
<span>Any other computer. It records your work and sends it to the hub.</span></label>
</div>
<label for="vault">Vault folder (hub)<span class="hint">Private career data. Keep it outside the cvprism code folder.</span></label>
<input type="text" id="vault" name="vault" value="{v.get('vault', default_vault)}">
</fieldset>
<fieldset><legend>Where your cards sync</legend>
<label for="adapters">Sync transports<span class="hint">Comma-separated: git:&lt;private repo URL&gt;, gdrive:&lt;synced folder&gt;, usb, syncthing:&lt;folder&gt;. A spoke needs at least one. Leave blank on a hub that is your only computer.</span></label>
<input type="text" id="adapters" name="adapters" value="{v.get('adapters', '')}">
<label for="watch">Project folders to watch<span class="hint">Comma-separated. cvprism notices new libraries and tools here, never file contents.</span></label>
<input type="text" id="watch" name="watch" value="{v.get('watch', '')}">
<label class="check"><input type="checkbox" name="claude" {checked}> Learn from my Claude Code sessions (skills and methods only, never code or data)</label>
</fieldset>
<button type="submit">Set up this computer</button>
</form>""")


def done_html(cfg: dict) -> bytes:
    name = html.escape(cfg["name"])
    role = html.escape(cfg["role"])
    nxt = ("cvprism log \"Built X with Y\" --skill y --depth 3\ncvprism install      # hooks + background agent"
           if cfg["role"] == "hub" else "cvprism sync\ncvprism install      # hooks + background agent")
    return _page(f"""<div class="done">
<h1>{name} is ready</h1>
<p class="lede">This computer is set up as a <b>{role}</b> (device id <code>{html.escape(cfg['device_id'])}</code>). You can close this tab.</p>
<p>Next, in a terminal:</p>
<pre>{html.escape(nxt)}</pre></div>""", title="cvprism is ready")


class WizardServer:
    def __init__(self, port: int = 0, force: bool = False):
        self.token = secrets.token_urlsafe(18)
        self.done = threading.Event()
        self.result: dict | None = None
        self.force = force
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # keep the terminal quiet
                pass

            def _host_ok(self) -> bool:
                host = (self.headers.get("Host") or "").split(":")[0]
                return host in ("127.0.0.1", "localhost")

            def _send(self, code: int, body: bytes) -> None:
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if not self._host_ok() or q.get("t", [""])[0] != outer.token:
                    return self._send(403, _page("<h1>Open the link printed in your terminal</h1>"))
                self._send(200, form_html(outer.token))

            def do_POST(self):  # noqa: N802
                n = min(int(self.headers.get("Content-Length") or 0), 64_000)
                f = {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8")).items()}
                if not self._host_ok() or f.get("token") != outer.token or urllib.parse.urlparse(self.path).path != "/setup":
                    return self._send(403, _page("<h1>This form has expired</h1>"))
                split = lambda s: [x.strip() for x in (s or "").split(",") if x.strip()]  # noqa: E731
                role = f.get("role", "hub")
                try:
                    cfg = wizard.configure(
                        name=(f.get("name") or "").strip() or "device", role=role,
                        vault_path=Path(f["vault"]) if role == "hub" and f.get("vault") else None,
                        adapters=split(f.get("adapters")), watch_paths=split(f.get("watch")),
                        claude_session=bool(f.get("claude")), force=outer.force)
                except wizard.SetupError as e:
                    return self._send(400, form_html(outer.token, f, str(e)))
                outer.result = cfg
                self._send(200, done_html(cfg))
                outer.done.set()

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/?t={self.token}"
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def run(force: bool = False, open_browser: bool = True) -> dict | None:
    import webbrowser

    s = WizardServer(force=force)
    s.start()
    print(f"Open this link to set up cvprism: {s.url}")
    if open_browser:
        webbrowser.open(s.url)
    try:
        s.done.wait()
        import time

        time.sleep(0.5)  # let the browser receive the confirmation page
    except KeyboardInterrupt:
        pass
    finally:
        s.stop()
    return s.result
