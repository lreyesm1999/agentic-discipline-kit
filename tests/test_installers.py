"""The one-line installers verify what they download and install both commands for the user.

Each test serves a fake release over HTTP, laid out like GitHub's (``latest/download/<asset>``
and ``download/v<version>/<asset>``), and points the installer at it through
``AGENTIC_DISCIPLINE_RELEASES_URL``. Nothing touches the network or the real user PATH.
"""

from __future__ import annotations

import hashlib
import io
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import threading
import zipfile
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = ROOT / "scripts" / "install.sh"
INSTALL_PS1 = ROOT / "scripts" / "install.ps1"
LINUX_ASSET = "agentic-discipline-Linux-X64.tar.gz"
WINDOWS_ASSET = "agentic-discipline-Windows-X64.zip"
CSC = (
    Path(os.environ.get("WINDIR", r"C:\Windows"))
    / "Microsoft.NET"
    / "Framework64"
    / "v4.0.30319"
    / "csc.exe"
)

linux_x64 = pytest.mark.skipif(
    not (sys.platform.startswith("linux") and platform.machine() in {"x86_64", "AMD64"})
    or shutil.which("curl") is None,
    reason="install.sh downloads the standalone build only on Linux x64 (and needs curl here)",
)
windows = pytest.mark.skipif(
    sys.platform != "win32" or not CSC.is_file(),
    reason="install.ps1 runs on Windows; the fake executables are built with the .NET Framework compiler",
)


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


@pytest.fixture
def release(tmp_path: Path) -> Iterator[tuple[Path, str]]:
    """A directory served over HTTP; returns (directory, base URL of the releases page)."""

    served = tmp_path / "releases"
    served.mkdir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(served)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield served, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _publish(served: Path, tag: str | None, asset: str, payload: bytes, sums: str | None) -> None:
    folder = served / ("latest/download" if tag is None else f"download/{tag}")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / asset).write_bytes(payload)
    if sums is not None:
        (folder / "SHA256SUMS").write_text(sums, encoding="utf-8")


def _sums(asset: str, payload: bytes) -> str:
    return f"{hashlib.sha256(b'sbom').hexdigest()}  sbom.json\n{hashlib.sha256(payload).hexdigest()}  {asset}\n"


# --- install.sh -------------------------------------------------------------------------


def _linux_archive(
    version: str,
    commands: tuple[str, ...] = ("agentic-discipline", "agentic"),
    body: str | None = None,
) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for command in commands:
            script = ("#!/bin/sh\n" + (body or f"echo '{command} {version}'\n")).encode()
            info = tarfile.TarInfo(command)
            info.size = len(script)
            info.mode = 0o755
            archive.addfile(info, io.BytesIO(script))
    return buffer.getvalue()


def _run_sh(base: str, bindir: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "AGENTIC_DISCIPLINE_RELEASES_URL": base,
        "AGENTIC_DISCIPLINE_INSTALL_DIR": str(bindir),
        **env,
    }
    if "AGENTIC_DISCIPLINE_VERSION" not in env:
        environment.pop("AGENTIC_DISCIPLINE_VERSION", None)
    return subprocess.run(
        ["sh", str(INSTALL_SH), *args], env=environment, capture_output=True, text=True, timeout=120
    )


@linux_x64
def test_sh_installs_the_latest_release_after_checking_its_checksum(
    release: tuple[Path, str], tmp_path: Path
) -> None:
    served, base = release
    payload = _linux_archive("9.9.9")
    _publish(served, None, LINUX_ASSET, payload, _sums(LINUX_ASSET, payload))
    bindir = tmp_path / "bin"

    completed = _run_sh(base, bindir)

    assert completed.returncode == 0, completed.stderr
    assert "Checksum verified" in completed.stdout
    assert "Installed agentic-discipline 9.9.9" in completed.stdout
    for command in ("agentic-discipline", "agentic"):
        installed = bindir / command
        assert os.access(installed, os.X_OK)
        assert subprocess.run(
            [str(installed), "--version"], capture_output=True, text=True
        ).stdout.strip() == (f"{command} 9.9.9")
    assert not list(bindir.glob(".*.new"))


@linux_x64
def test_sh_installs_a_pinned_version_from_its_tag(
    release: tuple[Path, str], tmp_path: Path
) -> None:
    served, base = release
    latest = _linux_archive("9.9.9")
    pinned = _linux_archive("2.1.0")
    _publish(served, None, LINUX_ASSET, latest, _sums(LINUX_ASSET, latest))
    _publish(served, "v2.1.0", LINUX_ASSET, pinned, _sums(LINUX_ASSET, pinned))
    bindir = tmp_path / "bin"

    completed = _run_sh(base, bindir, AGENTIC_DISCIPLINE_VERSION="v2.1.0")

    assert completed.returncode == 0, completed.stderr
    assert f"{base}/download/v2.1.0/{LINUX_ASSET}" in completed.stdout
    assert (bindir / "agentic").read_text().strip().endswith("echo 'agentic 2.1.0'")


@linux_x64
@pytest.mark.parametrize(
    ("sums", "message"),
    [
        (f"{'0' * 64}  {LINUX_ASSET}\n", "checksum mismatch"),
        (f"{'0' * 64}  sbom.json\n", "has no line for"),
        (None, "cannot be verified"),
    ],
)
def test_sh_installs_nothing_it_cannot_verify(
    release: tuple[Path, str], tmp_path: Path, sums: str | None, message: str
) -> None:
    served, base = release
    _publish(served, None, LINUX_ASSET, _linux_archive("9.9.9"), sums)
    bindir = tmp_path / "bin"

    completed = _run_sh(base, bindir)

    assert completed.returncode == 1
    assert message in completed.stderr
    assert "nothing was installed" in completed.stderr
    assert not bindir.exists()


@linux_x64
def test_sh_refuses_an_archive_without_both_commands(
    release: tuple[Path, str], tmp_path: Path
) -> None:
    served, base = release
    payload = _linux_archive("9.9.9", commands=("agentic-discipline",))
    _publish(served, None, LINUX_ASSET, payload, _sums(LINUX_ASSET, payload))
    bindir = tmp_path / "bin"

    completed = _run_sh(base, bindir)

    assert completed.returncode == 1
    assert "does not contain agentic" in completed.stderr
    assert not bindir.exists()


@linux_x64
def test_sh_reports_a_missing_release(release: tuple[Path, str], tmp_path: Path) -> None:
    _, base = release

    completed = _run_sh(base, tmp_path / "bin", AGENTIC_DISCIPLINE_VERSION="0.0.1")

    assert completed.returncode == 1
    assert f"could not download {base}/download/v0.0.1/{LINUX_ASSET}" in completed.stderr


@linux_x64
def test_sh_says_how_to_reach_a_directory_that_is_not_on_path(
    release: tuple[Path, str], tmp_path: Path
) -> None:
    served, base = release
    payload = _linux_archive("9.9.9")
    _publish(served, None, LINUX_ASSET, payload, _sums(LINUX_ASSET, payload))
    bindir = tmp_path / "elsewhere"

    completed = _run_sh(base, bindir, PATH="/usr/bin:/bin")

    assert completed.returncode == 0, completed.stderr
    assert f'export PATH="{bindir}:$PATH"' in completed.stdout


@linux_x64
def test_sh_uninstall_removes_only_what_it_installed(
    release: tuple[Path, str], tmp_path: Path
) -> None:
    served, base = release
    payload = _linux_archive("9.9.9")
    _publish(served, None, LINUX_ASSET, payload, _sums(LINUX_ASSET, payload))
    bindir = tmp_path / "bin"
    assert _run_sh(base, bindir).returncode == 0
    (bindir / "other-tool").write_text("keep me", encoding="utf-8")

    completed = _run_sh(base, bindir, "--uninstall")

    assert completed.returncode == 0, completed.stderr
    assert not (bindir / "agentic-discipline").exists()
    assert not (bindir / "agentic").exists()
    assert (bindir / "other-tool").read_text(encoding="utf-8") == "keep me"
    assert "Nothing to remove" in _run_sh(base, bindir, "--uninstall").stdout


_UNRUNNABLE = (
    "echo \"libm.so.6: version 'GLIBC_2.38' not found (required by libpython3.12.so.1.0)\" >&2\n"
    "exit 255\n"
)
_TOOLS = (
    "sh awk cat chmod cp curl cut dirname gzip head mkdir mktemp mv rm sed sha256sum sort tar tr "
    "uname"
).split()


def _toolbox(tmp_path: Path, **extra: str) -> str:
    """A PATH with only the tools install.sh needs, plus fake ones: uv and pipx stay absent."""

    box = tmp_path / "toolbox"
    box.mkdir()
    for tool in _TOOLS:
        found = shutil.which(tool)
        if found:
            (box / tool).symlink_to(found)
    for name, script in extra.items():
        (box / name).write_text("#!/bin/sh\n" + script, encoding="utf-8")
        (box / name).chmod(0o755)
    return str(box)


@linux_x64
def test_sh_leaves_an_existing_install_alone_when_the_new_build_does_not_run(
    release: tuple[Path, str], tmp_path: Path
) -> None:
    served, base = release
    payload = _linux_archive("9.9.9", body=_UNRUNNABLE)
    _publish(served, None, LINUX_ASSET, payload, _sums(LINUX_ASSET, payload))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "agentic-discipline").write_text("#!/bin/sh\necho 'previous'\n", encoding="utf-8")

    completed = _run_sh(base, bindir, PATH=_toolbox(tmp_path))

    assert completed.returncode == 1
    assert "GLIBC_2.38" in completed.stderr
    assert "pipx install agentic-discipline-kit" in completed.stderr
    assert sorted(path.name for path in bindir.iterdir()) == ["agentic-discipline"]
    assert "previous" in (bindir / "agentic-discipline").read_text(encoding="utf-8")


@linux_x64
def test_sh_falls_back_to_pypi_when_the_build_does_not_run(
    release: tuple[Path, str], tmp_path: Path
) -> None:
    served, base = release
    payload = _linux_archive("2.1.0", body=_UNRUNNABLE)
    _publish(served, "v2.1.0", LINUX_ASSET, payload, _sums(LINUX_ASSET, payload))
    calls = tmp_path / "uv-calls.txt"
    path = _toolbox(tmp_path, uv=f'echo "$*" >> "{calls}"\n')
    bindir = tmp_path / "bin"

    completed = _run_sh(base, bindir, PATH=path, AGENTIC_DISCIPLINE_VERSION="2.1.0")

    assert completed.returncode == 0, completed.stderr
    assert "GLIBC_2.38" in completed.stdout + completed.stderr
    assert (
        calls.read_text(encoding="utf-8").strip()
        == "tool install --force agentic-discipline-kit==2.1.0"
    )
    assert not bindir.exists()


@pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX sh")
def test_sh_rejects_an_unknown_argument(tmp_path: Path) -> None:
    completed = _run_sh("http://127.0.0.1:9", tmp_path / "bin", "--yes")

    assert completed.returncode == 1
    assert "unknown argument '--yes'" in completed.stderr


# --- install.ps1 ------------------------------------------------------------------------

_FAKE_EXE = """
class Program {
    static int Main(string[] args) {
        System.Console.WriteLine("NAME VERSION");
        return EXIT_CODE;
    }
}
"""


def _windows_archive(
    tmp_path: Path, version: str, commands: tuple[str, ...], exit_code: int = 0
) -> bytes:
    build = tmp_path / f"build-{version}-{exit_code}"
    build.mkdir(exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for command in commands:
            name = command.removesuffix(".exe")
            source = build / f"{name}.cs"
            source.write_text(
                _FAKE_EXE.replace("NAME VERSION", f"{name} {version}").replace(
                    "EXIT_CODE", str(exit_code)
                ),
                encoding="utf-8",
            )
            binary = build / command
            subprocess.run(
                [str(CSC), "/nologo", "/target:exe", f"/out:{binary}", str(source)],
                check=True,
                capture_output=True,
            )
            archive.write(binary, command)
    return buffer.getvalue()


def _powershells() -> list[str]:
    return [shell for shell in ("powershell", "pwsh") if shutil.which(shell)]


def _run_ps1(
    shell: str, base: str, bindir: Path, *args: str, piped: bool = False, **env: str
) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "AGENTIC_DISCIPLINE_RELEASES_URL": base,
        "AGENTIC_DISCIPLINE_INSTALL_DIR": str(bindir),
        "AGENTIC_DISCIPLINE_NO_MODIFY_PATH": "1",
        **env,
    }
    if "AGENTIC_DISCIPLINE_VERSION" not in env:
        environment.pop("AGENTIC_DISCIPLINE_VERSION", None)
    if piped:
        # The documented one-liners run the downloaded text in the user's own session: piped
        # into Invoke-Expression, or as a script block when it takes -Uninstall. An `exit` in
        # either would end this host before the marker below is printed.
        text = f"(Get-Content -Raw -LiteralPath '{INSTALL_PS1}')"
        if args:
            run = f"& ([scriptblock]::Create({text})) {' '.join(args)}"
        else:
            run = f"{text} | Invoke-Expression"
        command = [shell, "-NoProfile", "-Command", f"{run}; Write-Output 'HOST STILL RUNNING'"]
    else:
        command = [
            shell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(INSTALL_PS1),
            *args,
        ]
    return subprocess.run(command, env=environment, capture_output=True, text=True, timeout=300)


@windows
@pytest.mark.parametrize("shell", _powershells())
def test_ps1_installs_the_latest_release_after_checking_its_checksum(
    release: tuple[Path, str], tmp_path: Path, shell: str
) -> None:
    served, base = release
    payload = _windows_archive(tmp_path, "9.9.9", ("agentic-discipline.exe", "agentic.exe"))
    _publish(served, None, WINDOWS_ASSET, payload, _sums(WINDOWS_ASSET, payload))
    bindir = tmp_path / "bin"

    completed = _run_ps1(shell, base, bindir, piped=True)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Checksum verified" in completed.stdout
    assert "Installed agentic-discipline 9.9.9" in completed.stdout
    assert "HOST STILL RUNNING" in completed.stdout
    for command in ("agentic-discipline", "agentic"):
        version = subprocess.run(
            [str(bindir / f"{command}.exe"), "--version"], capture_output=True, text=True
        )
        assert version.stdout.strip() == f"{command} 9.9.9"


@windows
@pytest.mark.parametrize("shell", _powershells())
def test_ps1_installs_a_pinned_version_from_its_tag(
    release: tuple[Path, str], tmp_path: Path, shell: str
) -> None:
    served, base = release
    payload = _windows_archive(tmp_path, "2.1.0", ("agentic-discipline.exe", "agentic.exe"))
    _publish(served, "v2.1.0", WINDOWS_ASSET, payload, _sums(WINDOWS_ASSET, payload))
    bindir = tmp_path / "bin"

    completed = _run_ps1(shell, base, bindir, AGENTIC_DISCIPLINE_VERSION="2.1.0")

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert f"{base}/download/v2.1.0/{WINDOWS_ASSET}" in completed.stdout
    assert "Installed agentic-discipline 2.1.0" in completed.stdout


@windows
@pytest.mark.parametrize(
    ("sums", "message"),
    [
        (f"{'0' * 64}  {WINDOWS_ASSET}\n", "Checksum mismatch"),
        (f"{'0' * 64}  sbom.json\n", "has no line for"),
        (None, "cannot be verified"),
    ],
)
def test_ps1_installs_nothing_it_cannot_verify(
    release: tuple[Path, str], tmp_path: Path, sums: str | None, message: str
) -> None:
    served, base = release
    payload = _windows_archive(tmp_path, "9.9.9", ("agentic-discipline.exe", "agentic.exe"))
    _publish(served, None, WINDOWS_ASSET, payload, sums)
    bindir = tmp_path / "bin"

    completed = _run_ps1(_powershells()[0], base, bindir)

    assert completed.returncode != 0
    output = completed.stdout + completed.stderr
    assert message in output
    assert "nothing was installed" in output
    assert not bindir.exists()


@windows
def test_ps1_refuses_an_archive_without_both_commands(
    release: tuple[Path, str], tmp_path: Path
) -> None:
    served, base = release
    payload = _windows_archive(tmp_path, "9.9.9", ("agentic-discipline.exe",))
    _publish(served, None, WINDOWS_ASSET, payload, _sums(WINDOWS_ASSET, payload))
    bindir = tmp_path / "bin"

    completed = _run_ps1(_powershells()[0], base, bindir)

    assert completed.returncode != 0
    assert "does not contain agentic.exe" in completed.stdout + completed.stderr
    assert not bindir.exists()


@windows
def test_ps1_leaves_an_existing_install_alone_when_the_new_build_does_not_run(
    release: tuple[Path, str], tmp_path: Path
) -> None:
    served, base = release
    payload = _windows_archive(
        tmp_path, "9.9.9", ("agentic-discipline.exe", "agentic.exe"), exit_code=3
    )
    _publish(served, None, WINDOWS_ASSET, payload, _sums(WINDOWS_ASSET, payload))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "agentic-discipline.exe").write_bytes(b"previous")

    completed = _run_ps1(_powershells()[0], base, bindir)

    assert completed.returncode != 0
    assert "does not run on this system" in completed.stdout + completed.stderr
    assert sorted(path.name for path in bindir.iterdir()) == ["agentic-discipline.exe"]
    assert (bindir / "agentic-discipline.exe").read_bytes() == b"previous"


@windows
def test_ps1_uninstall_removes_only_what_it_installed(
    release: tuple[Path, str], tmp_path: Path
) -> None:
    served, base = release
    payload = _windows_archive(tmp_path, "9.9.9", ("agentic-discipline.exe", "agentic.exe"))
    _publish(served, None, WINDOWS_ASSET, payload, _sums(WINDOWS_ASSET, payload))
    bindir = tmp_path / "bin"
    shell = _powershells()[0]
    assert _run_ps1(shell, base, bindir).returncode == 0
    (bindir / "other-tool.txt").write_text("keep me", encoding="utf-8")

    completed = _run_ps1(shell, base, bindir, "-Uninstall", piped=True)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "HOST STILL RUNNING" in completed.stdout
    assert not (bindir / "agentic-discipline.exe").exists()
    assert not (bindir / "agentic.exe").exists()
    assert (bindir / "other-tool.txt").read_text(encoding="utf-8") == "keep me"
