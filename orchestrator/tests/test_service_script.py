"""dist/bin/service.sh（launchd常時起動管理）と dist/bin/lib.sh のテスト（issue #318）。

launchctlは実際のlaunchdを触らないよう、PATH先頭に置いたフェイクで差し替える。
plist生成・二重起動防止・LAN_IP/TAILSCALE_IPの検証を、subprocessで実行して検証する。
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest

DIST_BIN = Path(__file__).resolve().parents[2] / "dist" / "bin"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "producer-desk"
    (r / "bin").mkdir(parents=True)
    (r / "config").mkdir()
    (r / "config" / "projects.yaml").write_text("projects: []\n", encoding="utf-8")
    # start.shはbackend_start.sh・frontend_start.sh（proc.sh・lib.shを読み込む）へ委譲する（#326）。
    for f in (
        "service.sh",
        "start.sh",
        "backend_start.sh",
        "frontend_start.sh",
        "proc.sh",
        "lib.sh",
    ):
        shutil.copy2(DIST_BIN / f, r / "bin" / f)
        (r / "bin" / f).chmod(0o755)
    return r


def _fake_launchctl(tmp_path: Path, registered: bool) -> Path:
    d = tmp_path / "fakebin"
    d.mkdir(exist_ok=True)
    f = d / "launchctl"
    # `print` のみ登録状態を返す。それ以外は成功扱い。
    f.write_text(
        f'#!/bin/bash\n[ "$1" = print ] && exit {0 if registered else 1}\nexit 0\n',
        encoding="utf-8",
    )
    f.chmod(0o755)
    return d


def _run(
    root: Path, script: str, *args: str, env: dict[str, str] | None = None, fake: Path | None = None
):
    e = {k: v for k, v in os.environ.items() if k not in ("LAN_IP", "TAILSCALE_IP")}
    e["SERVICE_PATH"] = "/opt/test/bin:/usr/bin:/bin"
    if fake is not None:
        e["PATH"] = f"{fake}:{e['PATH']}"
    e.update(env or {})
    return subprocess.run(
        ["/bin/bash", str(root / "bin" / script), *args],
        capture_output=True,
        text=True,
        env=e,
        cwd=root,
    )


@pytest.mark.parametrize("name", ["orchestrator", "dashboard"])
def test_render_plist_is_valid_and_has_expected_keys(root: Path, name: str):
    result = _run(root, "service.sh", "render-plist", name)
    assert result.returncode == 0, result.stderr
    data = plistlib.loads(result.stdout.encode())
    assert data["Label"] == f"com.nosetech.producer-desk.{name}"
    assert data["RunAtLoad"] is True
    assert data["KeepAlive"] is True
    assert data["ThrottleInterval"] == 30
    assert data["EnvironmentVariables"]["PATH"] == "/opt/test/bin:/usr/bin:/bin"
    assert data["ProgramArguments"][-2:] == ["run", name]
    assert data["ProgramArguments"][1] == str(root / "bin" / "service.sh")
    assert data["WorkingDirectory"] == str(root)
    # 本体ログ（日次ローテーション対象）とは別ファイルにする
    stderr_log = data["StandardErrorPath"]
    assert stderr_log == str(root / "logs" / f"{name}.launchd.stderr.log")
    assert data["StandardOutPath"] == stderr_log


def test_render_plist_rejects_unknown_service(root: Path):
    result = _run(root, "service.sh", "render-plist", "litellm")
    assert result.returncode == 2


def test_unknown_subcommand_shows_usage(root: Path):
    result = _run(root, "service.sh", "bogus")
    assert result.returncode == 2
    assert "使い方" in result.stderr


def test_start_sh_refuses_when_registered_in_launchd(root: Path, tmp_path: Path):
    fake = _fake_launchctl(tmp_path, registered=True)
    result = _run(root, "start.sh", fake=fake)
    assert result.returncode == 1
    assert "service.sh" in result.stderr
    assert not (root / "logs" / "orchestrator.pid").exists()


def test_start_sh_not_blocked_by_launchd_when_unregistered(root: Path, tmp_path: Path):
    fake = _fake_launchctl(tmp_path, registered=False)
    # LAN_IPとTAILSCALE_IPの同時指定エラーまで進む（=launchd検査を通過している）
    result = _run(
        root,
        "start.sh",
        env={"LAN_IP": "192.168.1.2", "TAILSCALE_IP": "100.0.0.1"},
        fake=fake,
    )
    assert result.returncode == 1
    assert "同時に指定できません" in result.stderr


def test_service_sh_run_rejects_lan_and_tailscale_together(root: Path):
    result = _run(
        root,
        "service.sh",
        "run",
        "dashboard",
        env={"LAN_IP": "192.168.1.2", "TAILSCALE_IP": "100.0.0.1"},
    )
    assert result.returncode == 1
    assert "同時に指定できません" in result.stderr


def test_service_sh_run_fails_without_projects_yaml(root: Path):
    (root / "config" / "projects.yaml").unlink()
    result = _run(root, "service.sh", "run", "orchestrator")
    assert result.returncode == 1
    assert "projects.yaml" in result.stderr


def test_service_install_fails_when_manually_running(root: Path, tmp_path: Path):
    # 生存プロセスのPIDをPIDファイルに書く（このテスト自身のPID）
    (root / "logs").mkdir()
    (root / "logs" / "orchestrator.pid").write_text(str(os.getpid()), encoding="utf-8")
    result = _run(root, "service.sh", "install", fake=_fake_launchctl(tmp_path, False))
    # macOS以外ではrequire_macosで先に失敗するが、いずれも非0で失敗する
    assert result.returncode == 1
    if os.uname().sysname == "Darwin":
        assert "stop.sh" in result.stderr
