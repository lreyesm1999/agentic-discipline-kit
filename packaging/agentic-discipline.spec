# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path


project_root = Path(SPECPATH).parent
data_paths = [
    ("AGENTS.md", "."),
    ("MASTER_PROMPT.md", "."),
    ("agentic", "agentic"),
    ("disciplines", "disciplines"),
    ("skills", "skills"),
    ("policies", "policies"),
    ("schemas", "schemas"),
    ("templates", "templates"),
    ("config/examples", "config/examples"),
    ("config/profiles", "config/profiles"),
    ("config/risk-weights.json", "config"),
]
datas = [(str(project_root / source), destination) for source, destination in data_paths]


def executable(entrypoint, name):
    """One self-contained executable per console command, sharing the same data."""

    analysis = Analysis(
        [str(project_root / "packaging" / entrypoint)],
        pathex=[str(project_root / "src")],
        binaries=[],
        datas=datas,
        hiddenimports=[],
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=[],
        noarchive=False,
        optimize=0,
    )
    return EXE(
        PYZ(analysis.pure),
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
        [],
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=True,
    )


# `agentic-discipline` installs and checks the discipline; `agentic` is the
# project control plane. Both ship in every standalone archive.
discipline = executable("entrypoint.py", "agentic-discipline")
control = executable("entrypoint_control.py", "agentic")
