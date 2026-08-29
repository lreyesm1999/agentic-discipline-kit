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

a = Analysis(
    [str(project_root / "packaging" / "entrypoint.py")],
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
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="agentic-discipline",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
