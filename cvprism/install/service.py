"""Background agent at login, per OS, without admin rights (ADR-013).

Windows uses the per-user Run registry key (HKCU) rather than Task Scheduler, because ONLOGON
scheduled tasks need elevation on many machines.
"""
from __future__ import annotations

import platform
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

LABEL = "dev.cvprism.agent"
RUN_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"


@dataclass
class Action:
    kind: str  # "write" | "run" | "remove"
    path: Path | None = None
    content: str = ""
    cmd: list[str] = field(default_factory=list)


def launchd_plist(argv: list[str]) -> str:
    args = "\n".join(f"    <string>{a}</string>" for a in argv)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
{args}
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
"""


def systemd_unit(argv: list[str]) -> str:
    return f"""[Unit]
Description=cvprism capture agent

[Service]
ExecStart={' '.join(argv)}
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
"""


def windows_run_value(pythonw: str) -> str:
    return f'"{pythonw}" -m cvprism agent'


def current_os() -> str:
    s = platform.system().lower()
    return {"darwin": "macos", "windows": "windows"}.get(s, "linux")


def default_argv() -> list[str]:
    exe = Path(sys.executable)
    if current_os() == "windows":
        pyw = exe.with_name("pythonw.exe")
        return [str(pyw if pyw.exists() else exe), "-m", "cvprism", "agent"]
    return [str(exe), "-m", "cvprism", "agent"]


def plan(os_name: str, argv: list[str]) -> list[Action]:
    if os_name == "macos":
        p = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        return [Action("write", p, launchd_plist(argv)),
                Action("run", cmd=["launchctl", "unload", str(p)]),
                Action("run", cmd=["launchctl", "load", "-w", str(p)])]
    if os_name == "windows":
        return [Action("run", cmd=["reg", "add", RUN_KEY, "/v", "cvprism-agent", "/t", "REG_SZ",
                                   "/d", windows_run_value(argv[0]), "/f"])]
    p = Path.home() / ".config" / "systemd" / "user" / "cvprism-agent.service"
    return [Action("write", p, systemd_unit(argv)),
            Action("run", cmd=["systemctl", "--user", "daemon-reload"]),
            Action("run", cmd=["systemctl", "--user", "enable", "--now", "cvprism-agent.service"])]


def unplan(os_name: str) -> list[Action]:
    if os_name == "macos":
        p = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        return [Action("run", cmd=["launchctl", "unload", str(p)]), Action("remove", p)]
    if os_name == "windows":
        return [Action("run", cmd=["reg", "delete", RUN_KEY, "/v", "cvprism-agent", "/f"])]
    p = Path.home() / ".config" / "systemd" / "user" / "cvprism-agent.service"
    return [Action("run", cmd=["systemctl", "--user", "disable", "--now", "cvprism-agent.service"]),
            Action("remove", p)]


def execute(actions: list[Action]) -> list[str]:
    log = []
    for a in actions:
        if a.kind == "write":
            a.path.parent.mkdir(parents=True, exist_ok=True)
            a.path.write_text(a.content, encoding="utf-8")
            log.append(f"wrote {a.path}")
        elif a.kind == "remove":
            if a.path and a.path.exists():
                a.path.unlink()
                log.append(f"removed {a.path}")
        else:
            r = subprocess.run(a.cmd, capture_output=True, text=True)
            log.append(f"{' '.join(a.cmd[:3])}...: {'ok' if r.returncode == 0 else 'exit ' + str(r.returncode)}")
    return log
