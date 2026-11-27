"""Login service definitions (ADR-013). Generation is tested on every OS; registration is not run in tests."""
from cvprism.install import service


def test_launchd_plist():
    text = service.launchd_plist(["/venv/bin/cvprism", "agent"])
    assert "<key>RunAtLoad</key>" in text and "<string>agent</string>" in text and "dev.cvprism.agent" in text


def test_systemd_unit():
    text = service.systemd_unit(["/venv/bin/cvprism", "agent"])
    assert "ExecStart=/venv/bin/cvprism agent" in text and "WantedBy=default.target" in text
    assert "Restart=on-failure" in text


def test_windows_run_command_uses_pythonw_and_quotes():
    cmd = service.windows_run_value(r"C:\Users\A B\venv\Scripts\pythonw.exe")
    assert cmd == '"C:\\Users\\A B\\venv\\Scripts\\pythonw.exe" -m cvprism agent'


def test_plan_lists_actions_without_executing():
    plan = service.plan("linux", ["/venv/bin/cvprism", "agent"])
    assert plan[0].kind == "write" and plan[0].path.name == "cvprism-agent.service"
    assert any(a.kind == "run" and "systemctl" in a.cmd[0] for a in plan)
