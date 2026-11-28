"""`cvprism app`: a local browser app for people who don't use a terminal (ADR-018).

Security: binds 127.0.0.1 only; a one-time key in the URL becomes an HttpOnly, SameSite=Strict cookie;
every POST carries a CSRF token; the Host header must be localhost (DNS-rebinding defence); strict CSP; all
output escaped; downloads limited to the vault's build folder.
"""
from __future__ import annotations

import email.parser
import email.policy
import secrets
import tempfile
import threading
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .. import config, paths, yamlio
from . import pages

MAX_BODY = 25 * 1024 * 1024
COOKIE = "cvprism_app"


def _cfg() -> dict:
    return config.load_device()


def _vault(cfg: dict) -> Path | None:
    return Path(cfg["vault_path"]) if cfg.get("role") == "hub" and cfg.get("vault_path") else None


def _profile(cfg: dict) -> dict:
    v = _vault(cfg)
    if v and (v / "profile.yaml").is_file():
        return yamlio.load(v / "profile.yaml") or {}
    return {}


def _cards(cfg: dict) -> list[dict]:
    from ..hub.merge import read_cards
    from ..sync.outbox import Outbox

    v = _vault(cfg)
    own = list(Outbox(paths.outbox_dir(), cfg["device_id"]).iter_cards())
    if v is None:
        return own
    ids = {c["id"] for c in read_cards(v)}
    return read_cards(v) + [c for c in own if c["id"] not in ids]


def _with_levels(cards: list[dict], cfg: dict) -> list[dict]:
    from ..compile.evidence import LinkIndex, card_proof

    prof = _profile(cfg)
    v = _vault(cfg)
    idx = LinkIndex.load(v) if v else LinkIndex()
    return [dict(c, level=card_proof(c, prof, idx).level) for c in cards]


def _last_build(cfg: dict) -> str | None:
    v = _vault(cfg)
    if not v or not (v / "build").is_dir():
        return None
    dirs = sorted((d for d in (v / "build").glob("*/*") if d.is_dir() and (d / "build.json").exists()),
                  key=lambda d: d.stat().st_mtime)
    if not dirs:
        return None
    return datetime.fromtimestamp(dirs[-1].stat().st_mtime).strftime("%d %b %Y")


def _roles(cfg: dict) -> list[tuple[str, str]]:
    from ..compile.roles import load_role, starter_roles

    v = _vault(cfg)
    ids = list(starter_roles())
    if v and (v / "roles").is_dir():
        ids += [p.stem for p in (v / "roles").glob("*.yaml") if p.stem not in ids]
    out = []
    for rid in ids:
        try:
            out.append((rid, load_role(rid, v)["title"]))
        except Exception:  # noqa: BLE001 - a broken role file shouldn't take the page down
            continue
    return out


def _set_project(cfg: dict, ctx: str, visibility: str, url: str, display: str) -> str:
    from ..compile.evidence import is_https, normalise_repo_url
    from ..novelty.ids import slugify
    from ..schemas import errors

    v = _vault(cfg)
    if v is None:
        raise ValueError("Project settings live on your main computer.")
    slug = slugify(ctx)
    if not slug:
        raise ValueError("Give the project a short name.")
    if visibility not in ("public", "private", "local"):
        raise ValueError("Choose public, private or local.")
    url = normalise_repo_url(url) if url else ""
    if url and not is_https(url):
        raise ValueError("The link must start with https://")
    if visibility == "public" and not url:
        raise ValueError("A public project needs a link to its repository or page.")
    pf = v / "profile.yaml"
    prof = yamlio.load(pf) or {"v": 1, "person": {"name": "Your Name"}}
    projs = prof.setdefault("projects", [])
    p = next((x for x in projs if x.get("ctx") == slug), None)
    if p is None:
        p = {"ctx": slug, "display": display or slug.replace("-", " ").capitalize()}
        projs.append(p)
    if display:
        p["display"] = display
    p["visibility"] = visibility
    if url:
        p["url"] = url
    errs = errors("profile", prof)
    if errs:
        raise ValueError("; ".join(errs[:2]))
    yamlio.dump(prof, pf)
    return f"Saved: {p.get('display') or slug} is now {visibility}."


class AppServer:
    def __init__(self, port: int = 0):
        self.token = secrets.token_urlsafe(24)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            # ---- plumbing ----------------------------------------------------------------------------
            def _host_ok(self) -> bool:
                return (self.headers.get("Host") or "").split(":")[0] in ("127.0.0.1", "localhost")

            def _authed(self) -> bool:
                raw = self.headers.get("Cookie") or ""
                parts = dict(p.strip().split("=", 1) for p in raw.split(";") if "=" in p)
                return secrets.compare_digest(parts.get(COOKIE, ""), outer.token)

            def _send(self, code: int, body: bytes, ctype="text/html; charset=utf-8", extra=None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy",
                                 "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; form-action 'self'")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def _page(self, code: int, title: str, active: str, body: str):
                body = body.replace("{csrf}", outer.token)
                self._send(code, pages.layout(title, active, body))

            def _deny(self):
                self._send(403, pages.layout("Locked", "", "<h1>Open cvprism from the link in your terminal</h1>"
                                             "<p class='lede'>Run <code>cvprism app</code> again if you closed it.</p>"))

            def _form(self) -> tuple[dict, dict]:
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BODY:
                    raise ValueError("That file is too large (25 MB maximum).")
                raw = self.rfile.read(n)
                ctype = self.headers.get("Content-Type") or ""
                if ctype.startswith("multipart/form-data"):
                    msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
                        f"Content-Type: {ctype}\r\n\r\n".encode() + raw)
                    fields, files = {}, {}
                    for part in msg.iter_parts():
                        name = part.get_param("name", header="content-disposition")
                        if part.get_filename():
                            files[name] = (part.get_filename(), part.get_payload(decode=True) or b"")
                        else:
                            fields.setdefault(name, []).append((part.get_payload(decode=True) or b"").decode("utf-8", "replace"))
                    return fields, files
                return urllib.parse.parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True), {}

            # ---- GET ---------------------------------------------------------------------------------
            def do_GET(self):  # noqa: N802
                if not self._host_ok():
                    return self._deny()
                path = urllib.parse.urlparse(self.path).path
                if path.startswith("/k/"):
                    if secrets.compare_digest(path[3:], outer.token):
                        return self._send(303, b"", extra={
                            "Location": "/", "Set-Cookie": f"{COOKIE}={outer.token}; HttpOnly; SameSite=Strict; Path=/"})
                    return self._deny()
                if not self._authed():
                    return self._deny()
                try:
                    cfg = _cfg()
                except config.NotInitialised:
                    return self._page(200, "Set up", "/", "<h1>Set up cvprism first</h1>"
                                      "<p class='lede'>Run <code>cvprism init --web</code>, then open the app again.</p>")
                if path.startswith("/download/"):
                    return self._download(cfg, path[len("/download/"):])
                prof = _profile(cfg)
                if path == "/":
                    cards = _with_levels(_cards(cfg), cfg)
                    counts: dict = {}
                    for c in cards:
                        counts[c["level"]] = counts.get(c["level"], 0) + 1
                    return self._page(200, "Home", "/", pages.home((prof.get("person") or {}).get("name", ""),
                                                                   cfg["role"], counts, len(prof.get("projects") or []),
                                                                   _last_build(cfg)))
                if path == "/add":
                    return self._page(200, "Add evidence", "/add", pages.add_form(prof.get("projects") or []))
                if path == "/import":
                    return self._page(200, "Import", "/import", pages.import_form())
                if path == "/projects":
                    return self._page(200, "Projects", "/projects",
                                      pages.projects_page(prof.get("projects") or [], _vault(cfg) is not None))
                if path == "/cards":
                    rows = sorted(_with_levels(_cards(cfg), cfg), key=lambda c: c["t"], reverse=True)[:50]
                    return self._page(200, "My evidence", "/cards", pages.cards_page(rows))
                if path == "/build":
                    return self._page(200, "Build a CV", "/build",
                                      pages.build_form(_roles(cfg) if _vault(cfg) else [], _vault(cfg) is not None))
                return self._page(404, "Not found", "", "<h1>Page not found</h1>")

            def _download(self, cfg: dict, rel: str):
                v = _vault(cfg)
                rel = urllib.parse.unquote(rel)
                if v is None or not rel or "\\" in rel or rel.startswith("/") or ".." in Path(rel).parts:
                    return self._send(400, b"bad path", "text/plain")
                root = (v / "build").resolve()
                target = (root / rel).resolve()
                if not target.is_relative_to(root) or not target.is_file():
                    return self._send(404, b"not found", "text/plain")
                ctypes = {".pdf": "application/pdf", ".md": "text/markdown; charset=utf-8",
                          ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
                self._send(200, target.read_bytes(), ctypes.get(target.suffix, "application/octet-stream"),
                           {"Content-Disposition": f'attachment; filename="{target.name}"'})

            # ---- POST --------------------------------------------------------------------------------
            def do_POST(self):  # noqa: N802
                if not self._host_ok() or not self._authed():
                    return self._deny()
                try:
                    fields, files = self._form()
                except ValueError as e:
                    return self._page(413, "Too large", "", pages.message(str(e), True))
                one = lambda k: (fields.get(k) or [""])[0].strip()  # noqa: E731
                if not secrets.compare_digest(one("csrf"), outer.token):
                    return self._deny()
                cfg = _cfg()
                path = urllib.parse.urlparse(self.path).path
                if path == "/add":
                    return self._post_add(cfg, fields, one)
                if path == "/projects":
                    try:
                        msg = _set_project(cfg, one("ctx"), one("visibility") or "private", one("url"), one("display"))
                        err = False
                    except ValueError as e:
                        msg, err = str(e), True
                    prof = _profile(cfg)
                    return self._page(400 if err else 200, "Projects", "/projects",
                                      pages.projects_page(prof.get("projects") or [], True, msg, err))
                if path == "/import":
                    return self._post_import(cfg, files, one)
                if path == "/build":
                    return self._post_build(cfg, fields, one)
                return self._page(404, "Not found", "", "<h1>Page not found</h1>")

            def _post_add(self, cfg, fields, one):
                from ..capture.manual import LogError, log_entry

                prof = _profile(cfg)
                values = {k: one(k) for k in ("what", "skill", "depth", "result_metric", "result_value",
                                              "result_unit", "link", "project", "work", "use_ai")}
                skills = [s.strip() for s in values["skill"].split(",") if s.strip()]
                use_ai = bool(values["use_ai"])
                result = None
                if values["result_value"]:
                    result = f"{values['result_metric'] or 'result'}:{values['result_value']}:{values['result_unit']}"
                try:
                    if not use_ai and not skills:
                        raise LogError("Name at least one skill, or tick 'Let Claude polish the wording'.")
                    res = log_entry(values["what"], cfg=cfg, skills=skills, depth=int(values["depth"] or 2),
                                    result=result, work=bool(values["work"]), ctx=values["project"] or None,
                                    raw=not use_ai, links=[values["link"]] if values["link"] else None)
                except (LogError, ValueError) as e:
                    return self._page(400, "Add evidence", "/add",
                                      pages.add_form(prof.get("projects") or [], values, str(e), True))
                msg = "Saved. " + " ".join(m for m in res.messages if not m.startswith("cvprism:"))
                return self._page(200, "Add evidence", "/add", pages.add_form(prof.get("projects") or [], None, msg))

            def _post_import(self, cfg, files, one):
                from ..capture.importers import import_cv, import_linkedin

                kind = one("kind")
                name, data = files.get("file", ("", b""))
                if not data:
                    return self._page(400, "Import", "/import", pages.import_form("Choose a file to upload.", True))
                suffix = Path(name).suffix.lower()
                allowed = {".zip"} if kind == "linkedin" else {".docx", ".md", ".txt", ".pdf"}
                if suffix not in allowed:
                    return self._page(400, "Import", "/import",
                                      pages.import_form(f"Expected a {' or '.join(sorted(allowed))} file.", True))
                with tempfile.TemporaryDirectory() as td:
                    f = Path(td) / f"upload{suffix}"
                    f.write_bytes(data)
                    try:
                        fn = import_linkedin if kind == "linkedin" else import_cv
                        rep = fn(f, cfg, use_llm=bool(one("use_ai")))
                    except Exception as e:  # noqa: BLE001
                        return self._page(400, "Import", "/import", pages.import_form(f"Couldn't import: {e}", True))
                msg = (f"Imported: {rep.cards} new card(s), {rep.known} already known. "
                       f"Profile: +{rep.positions} position(s), +{rep.education} education, +{rep.certifications} "
                       f"certification(s). Imported lines are marked for review.")
                return self._page(200, "Import", "/import", pages.import_form(msg))

            def _post_build(self, cfg, fields, one):
                from ..compile.build import BuildError, build_cv
                from ..compile.jd import build_for_jd
                from ..compile.roles import RoleError

                v = _vault(cfg)
                if v is None:
                    return self._page(200, "Build a CV", "/build", pages.build_form([], False))
                formats = [f for f in fields.get("formats", []) if f in ("pdf", "docx", "md")] or ["pdf", "docx", "md"]
                role, jd = one("role"), (fields.get("jd") or [""])[0]
                try:
                    if jd.strip():
                        jd_dir = v / "build" / "_postings"
                        jd_dir.mkdir(parents=True, exist_ok=True)
                        jd_file = jd_dir / f"{datetime.now():%Y%m%d-%H%M%S}.txt"
                        jd_file.write_text(jd, encoding="utf-8")
                        res = build_for_jd(cfg, str(jd_file), use_llm=bool(one("use_ai")), formats=formats,
                                           base_role=role or None)
                    elif role:
                        res = build_cv(cfg, role, use_llm=bool(one("use_ai")), formats=formats)
                    else:
                        raise BuildError("Choose a role or paste a job posting.")
                except (BuildError, RoleError) as e:
                    return self._page(400, "Build a CV", "/build", pages.build_form(_roles(cfg), True, str(e), True))
                rel = res.out_dir.resolve().relative_to((v / "build").resolve()).as_posix()
                files = [f for f in ("cv.pdf", "cv.docx", "cv.md") if (res.out_dir / f).exists()]
                reports = {}
                for title, f in (("ATS read-back", "ats.md"), ("Gap report", "gaps.md"), ("Writing quality", "quality.md"),
                                 ("Removed claims", "rejected.md")):
                    p = res.out_dir / f
                    if p.exists():
                        reports[title] = p.read_text(encoding="utf-8")
                return self._page(200, "Your CV", "/build", pages.build_result(rel, files, res.log, reports))

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}/k/{self.token}"
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def run(open_browser: bool = True, port: int = 0) -> None:
    import webbrowser

    s = AppServer(port=port)
    s.start()
    print(f"cvprism app is running. Open: {s.url}")
    print("Keep this window open while you use it; press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(s.url)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        s.stop()
