"""Server-rendered pages for `cvprism app` (no JavaScript). Every value is escaped with h()."""
from __future__ import annotations

import html
from urllib.parse import quote

CSS = """
:root{--paper:#EEF1F5;--ink:#1A2230;--muted:#5A6577;--line:#CDD3DC;--act:#3346C8;--ok:#1E7A6E;--err:#B3261E;--field:#FFF;--link:#0052CC}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.spectrum{height:6px;background:linear-gradient(90deg,#3346C8 0 20%,#2A9D8F 20% 40%,#E9C46A 40% 60%,#F4A261 60% 80%,#E5533D 80%)}
header{background:#fff;border-bottom:1px solid var(--line)}
.bar{max-width:980px;margin:0 auto;padding:10px 24px;display:flex;gap:22px;align-items:center;flex-wrap:wrap}
.brand{font-weight:700;font-size:18px;margin-right:12px;color:var(--ink);text-decoration:none}
nav a{color:var(--muted);text-decoration:none;padding:6px 2px;border-bottom:2px solid transparent}
nav a[aria-current=page]{color:var(--ink);border-bottom-color:var(--act)}
nav{display:flex;gap:18px;flex-wrap:wrap}
main{max-width:980px;margin:0 auto;padding:32px 24px 72px}
h1{font-size:26px;line-height:1.25;margin:0 0 6px;font-weight:650}
h2{font-size:18px;margin:28px 0 10px}
.lede{color:var(--muted);margin:0 0 26px;max-width:68ch}
a{color:var(--link)}
.actions{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:8px 0 28px}
.action{display:block;background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px 18px;color:var(--ink);text-decoration:none}
.action b{display:block;font-size:16px;margin-bottom:4px}
.action span{color:var(--muted);font-size:14px}
.action:hover{border-color:var(--act)}
.facts{display:flex;gap:28px;flex-wrap:wrap;margin:0 0 8px;color:var(--muted)}
.facts strong{color:var(--ink);font-size:20px;display:block}
form.card,.panel{background:#fff;border:1px solid var(--line);border-radius:10px;padding:20px 22px;max-width:720px}
label{display:block;font-weight:550;margin:14px 0 4px}
.hint{display:block;color:var(--muted);font-weight:400;font-size:13.5px}
input[type=text],input[type=url],select,textarea{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:6px;background:var(--field);font:inherit;color:inherit}
textarea{min-height:170px}
.row{display:grid;grid-template-columns:2fr 1fr 1fr;gap:10px}
.check{display:flex;gap:8px;align-items:flex-start;font-weight:400}
button{margin-top:20px;background:var(--act);color:#fff;border:0;border-radius:6px;padding:10px 18px;font:inherit;font-weight:600;cursor:pointer}
button.small{margin:0;padding:6px 12px;font-size:14px}
:focus-visible{outline:3px solid #9AA8F0;outline-offset:2px}
.msg{border-left:4px solid var(--ok);background:#E7F4F1;padding:10px 14px;margin:0 0 22px;border-radius:0 6px 6px 0;max-width:720px}
.msg.err{border-left-color:var(--err);background:#FBEAE9}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:8px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid #E3E7ED;vertical-align:top}
th{font-weight:600;background:#F6F8FB}
td form{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
td select,td input[type=url]{width:auto;min-width:130px}
.lvl-public{color:var(--ok);font-weight:600}
.muted{color:var(--muted)}
.downloads{display:flex;gap:12px;flex-wrap:wrap;margin:6px 0 24px}
.downloads a{background:var(--act);color:#fff;text-decoration:none;padding:10px 16px;border-radius:6px;font-weight:600}
pre{background:#fff;border:1px solid var(--line);border-radius:8px;padding:14px 16px;white-space:pre-wrap;font-size:13.5px;max-width:900px}
@media (max-width:640px){.row{grid-template-columns:1fr}}
"""

NAV = [("/", "Home"), ("/add", "Add evidence"), ("/import", "Bring in what you have"), ("/projects", "Projects"),
       ("/cards", "My evidence"), ("/build", "Build a CV")]
DEPTHS = [("1", "I used it"), ("2", "I applied it in real work"), ("3", "I built something with it"),
          ("4", "I led it / it's in production"), ("5", "I published or taught it")]
LEVEL_TEXT = {"public": "Public proof", "confirmed": "Third-party confirmed", "captured": "Captured",
              "self-reported": "Self-reported"}


def h(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def layout(title: str, active: str, body: str) -> bytes:
    nav = "".join(f'<a href="{p}"{" aria-current=page" if p == active else ""}>{h(t)}</a>' for p, t in NAV)
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{h(title)} · cvprism</title>"
            f"<style>{CSS}</style></head><body><div class='spectrum' aria-hidden='true'></div>"
            f"<header><div class='bar'><a class='brand' href='/'>cvprism</a><nav aria-label='Main'>{nav}</nav></div>"
            f"</header><main>{body}</main></body></html>").encode("utf-8")


def message(text: str | None, error: bool = False) -> str:
    if not text:
        return ""
    return f"<p class='msg{' err' if error else ''}' role='{'alert' if error else 'status'}'>{h(text)}</p>"


def home(name: str, role: str, counts: dict, projects: int, last_build: str | None) -> str:
    total = sum(counts.values())
    facts = (f"<div class='facts'><div><strong>{total}</strong>evidence cards</div>"
             f"<div><strong>{counts.get('public', 0)}</strong>with public proof</div>"
             f"<div><strong>{projects}</strong>projects</div>"
             f"<div><strong>{h(last_build or 'none yet')}</strong>last CV</div></div>")
    who = h(name) if name and name != "Your Name" else "Welcome"
    where = ("This is your main computer: your CVs are built here." if role == "hub" else
             "This computer sends your evidence to your main computer, where CVs are built.")
    return f"""<h1>{who}</h1><p class="lede">{where} Everything stays on your computers.</p>{facts}
<h2>What would you like to do?</h2>
<div class="actions">
<a class="action" href="/add"><b>Add evidence</b><span>A paper, a talk, field work, a result, a skill you used.</span></a>
<a class="action" href="/import"><b>Bring in what you have</b><span>Your LinkedIn export or an old CV.</span></a>
<a class="action" href="/projects"><b>Projects</b><span>Choose which work gets public proof links.</span></a>
<a class="action" href="/build"><b>Build a CV</b><span>For a role, or tailored to a job posting.</span></a>
</div>"""


def add_form(projects: list[dict], values: dict | None = None, msg: str = "", error: bool = False) -> str:
    v = values or {}
    opts = "<option value=''>No project</option>" + "".join(
        f"<option value='{h(p['ctx'])}'{' selected' if v.get('project') == p['ctx'] else ''}>{h(p.get('display') or p['ctx'])}</option>"
        for p in projects)
    depth = "".join(f"<option value='{k}'{' selected' if str(v.get('depth', '2')) == k else ''}>{h(t)}</option>"
                    for k, t in DEPTHS)
    return f"""<h1>Add evidence</h1><p class="lede">One achievement at a time. Only write what you can stand behind:
numbers are kept only if you type them.</p>{message(msg, error)}
<form class="card" method="post" action="/add"><input type="hidden" name="csrf" value="{{csrf}}">
<label for="what">What did you do?<span class="hint">One sentence, e.g. "Calibrated a 2D flood model for the Hooghly estuary".</span></label>
<input type="text" id="what" name="what" required value="{h(v.get('what'))}">
<label for="skill">Skills<span class="hint">Comma-separated, e.g. "HEC-RAS, model calibration".</span></label>
<input type="text" id="skill" name="skill" value="{h(v.get('skill'))}">
<label for="depth">How deep did you go?</label><select id="depth" name="depth">{depth}</select>
<label>Result, if you measured one<span class="hint">e.g. metric "setup time", value "15", unit "min". Leave empty if there isn't one.</span></label>
<div class="row"><input type="text" name="result_metric" aria-label="Metric" placeholder="metric" value="{h(v.get('result_metric'))}">
<input type="text" name="result_value" aria-label="Value" placeholder="value" value="{h(v.get('result_value'))}">
<input type="text" name="result_unit" aria-label="Unit" placeholder="unit" value="{h(v.get('result_unit'))}"></div>
<label for="link">Proof link<span class="hint">Optional public https:// link: a DOI, repository, video, certificate page.</span></label>
<input type="url" id="link" name="link" value="{h(v.get('link'))}">
<label for="project">Project</label><select id="project" name="project">{opts}</select>
<label class="check"><input type="checkbox" name="work"{' checked' if v.get('work') else ''}> This isn't code (paper, talk, field work, award, teaching)</label>
<label class="check"><input type="checkbox" name="use_ai"{' checked' if v.get('use_ai') else ''}> Let Claude polish the wording (it can't add claims or numbers)</label>
<button type="submit">Save evidence</button></form>"""


def import_form(msg: str = "", error: bool = False) -> str:
    return f"""<h1>Bring in what you have</h1><p class="lede">Start from your LinkedIn data or an old CV. Imported
lines are marked for review, because they're self-reported.</p>{message(msg, error)}
<form class="card" method="post" action="/import" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{{csrf}}">
<label for="kind">What are you uploading?</label>
<select id="kind" name="kind"><option value="linkedin">LinkedIn data export (.zip)</option>
<option value="cv">An old CV (.docx, .md, .txt or .pdf)</option></select>
<label for="file">File<span class="hint">LinkedIn: Settings → Data privacy → Get a copy of your data.</span></label>
<input type="file" id="file" name="file" required>
<label class="check"><input type="checkbox" name="use_ai"> Let Claude read it more carefully (slower)</label>
<button type="submit">Import</button></form>"""


def projects_page(projects: list[dict], is_hub: bool, msg: str = "", error: bool = False) -> str:
    if not is_hub:
        return "<h1>Projects</h1><p class='lede'>Project settings live on your main computer.</p>"
    rows = []
    for p in projects:
        vis = p.get("visibility", "local")
        sel = "".join(f"<option value='{k}'{' selected' if vis == k else ''}>{t}</option>"
                      for k, t in (("public", "Public: show links"), ("private", "Private repository"),
                                   ("local", "Local only")))
        rows.append(f"<tr><td><b>{h(p.get('display') or p['ctx'])}</b><br><span class='muted'>{h(p['ctx'])}</span></td>"
                    f"<td><form method='post' action='/projects'><input type='hidden' name='csrf' value='{{csrf}}'>"
                    f"<input type='hidden' name='ctx' value='{h(p['ctx'])}'>"
                    f"<select name='visibility' aria-label='Visibility'>{sel}</select>"
                    f"<input type='url' name='url' aria-label='Repository or project link' placeholder='https://…' value='{h(p.get('url'))}'>"
                    f"<button class='small' type='submit'>Save</button></form></td></tr>")
    table = ("<table><thead><tr><th>Project</th><th>How it appears on your CV</th></tr></thead><tbody>"
             + "".join(rows) + "</tbody></table>") if rows else "<p class='muted'>No projects yet.</p>"
    return f"""<h1>Projects</h1><p class="lede">Public projects get blue proof links to the exact work. Private ones
keep every skill and show "(private repository)". Local work shows no label.</p>{message(msg, error)}{table}
<h2>Add a project</h2>
<form class="card" method="post" action="/projects"><input type="hidden" name="csrf" value="{{csrf}}">
<label for="ctx">Short name<span class="hint">e.g. flood-copilot</span></label><input type="text" id="ctx" name="ctx" required>
<label for="display">Name shown on your CV</label><input type="text" id="display" name="display">
<label for="visibility">Visibility</label><select id="visibility" name="visibility">
<option value="private">Private repository</option><option value="public">Public: show links</option><option value="local">Local only</option></select>
<label for="url">Link (public projects)</label><input type="url" id="url" name="url" placeholder="https://github.com/you/project">
<button type="submit">Add project</button></form>"""


def cards_page(rows: list[dict]) -> str:
    if not rows:
        return "<h1>My evidence</h1><p class='lede'>Nothing yet. <a href='/add'>Add your first piece of evidence</a>.</p>"
    body = "".join(
        f"<tr><td>{h(r['txt'])}</td><td>{h(', '.join(r['s']))}</td>"
        f"<td class='lvl-{h(r['level'])}'>{h(LEVEL_TEXT.get(r['level'], r['level']))}</td>"
        f"<td class='muted'>{h(r['t'][:10])}</td></tr>" for r in rows)
    return (f"<h1>My evidence</h1><p class='lede'>The {len(rows)} most recent cards. Each line on a CV points back to "
            f"one of these.</p><table><thead><tr><th>What you did</th><th>Skills</th><th>Proof</th><th>Date</th></tr>"
            f"</thead><tbody>{body}</tbody></table>")


def build_form(roles: list[tuple[str, str]], is_hub: bool, msg: str = "", error: bool = False) -> str:
    if not is_hub:
        return ("<h1>Build a CV</h1><p class='lede'>CVs are built on your main computer (the hub). Your evidence from "
                "this computer is sent there automatically.</p>")
    opts = "<option value=''>Choose a role…</option>" + "".join(
        f"<option value='{h(rid)}'>{h(title)}</option>" for rid, title in roles)
    fmts = "".join(f"<label class='check'><input type='checkbox' name='formats' value='{k}' checked> {t}</label>"
                   for k, t in (("pdf", "PDF"), ("docx", "Word"), ("md", "Markdown")))
    return f"""<h1>Build a CV</h1><p class="lede">Pick a role, or paste a job posting to tailor the CV to it. Every line
will point to its proof, and anything the evidence can't support is left out.</p>{message(msg, error)}
<form class="card" method="post" action="/build"><input type="hidden" name="csrf" value="{{csrf}}">
<label for="role">Role</label><select id="role" name="role">{opts}</select>
<label for="jd">…or paste a job posting<span class="hint">If you paste one, the CV is tailored to it and you get a gap report.</span></label>
<textarea id="jd" name="jd"></textarea>
<label>Formats</label>{fmts}
<label class="check"><input type="checkbox" name="use_ai" checked> Let Claude write the lines (honesty checks still apply)</label>
<button type="submit">Build my CV</button></form>"""


def build_result(rel_dir: str, files: list[str], log: list[str], reports: dict[str, str]) -> str:
    names = {"cv.pdf": "Download PDF", "cv.docx": "Download Word", "cv.md": "Download Markdown"}
    dl = "".join(f'<a href="/download/{quote(rel_dir + "/" + f)}">{names[f]}</a>' for f in files if f in names)
    rep = "".join(f"<h2>{h(title)}</h2><pre>{h(text)}</pre>" for title, text in reports.items() if text)
    return (f"<h1>Your CV is ready</h1><p class='lede'>{h(' · '.join(log[-3:]))}</p>"
            f"<div class='downloads'>{dl}</div>{rep}")
