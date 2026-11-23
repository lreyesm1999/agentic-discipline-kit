#!/usr/bin/env bash
# Build and smoke-test the Linux standalone executables inside a manylinux_2_28 container,
# so they need glibc 2.28 at most instead of whatever the CI runner happens to ship.
#
#   docker run --rm -v "$PWD:/src" -w /src quay.io/pypa/manylinux_2_28_x86_64 \
#     bash packaging/linux/build-standalone.sh
#
# The interpreters manylinux ships in /opt/python are linked statically, and PyInstaller
# needs a shared libpython, so the build uses a python-build-standalone 3.12 from uv instead.
# It targets an older glibc than manylinux_2_28 does, so the image sets the floor.
set -euo pipefail

archive="${1:-agentic-discipline-Linux-X64.tar.gz}"
work="${AGENTIC_STANDALONE_WORK:-/tmp/agentic-standalone}"

export UV_PYTHON_INSTALL_DIR="$work/python"
uv python install 3.12
uv venv --python 3.12 "$work/venv"
# shellcheck disable=SC1091
. "$work/venv/bin/activate"
uv pip install -e . pyinstaller
pyinstaller --clean --noconfirm packaging/agentic-discipline.spec

# `agentic adopt` creates the SQLite store with its full-text index and
# `knowledge query` searches it, so a frozen build without FTS5 fails here.
smoke="$(mktemp -d)"
./dist/agentic-discipline --version
./dist/agentic-discipline init --target "$smoke/standalone-smoke"
./dist/agentic --version
mkdir "$smoke/control-smoke" && echo "value = 1" > "$smoke/control-smoke/app.py"
./dist/agentic adopt "$smoke/control-smoke" --json
./dist/agentic --root "$smoke/control-smoke" knowledge query app.py --json
rm -rf "$smoke"

# Fail the build, not a user's install, when a bundled library asks for a newer glibc
# than the image provides.
max_glibc="$(ldd --version | sed -n '1s/.* //p')"
python - "$max_glibc" dist/agentic-discipline dist/agentic <<'PY'
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

floor = tuple(int(part) for part in sys.argv[1].split("."))
worst = (0,)
for executable in sys.argv[2:]:
    with tempfile.TemporaryDirectory() as extracted:
        # The bootloader is a plain ELF; the bundled libraries sit in its archive.
        reader = CArchiveReader(executable)
        files = [Path(executable)]
        for name in reader.toc:
            if name.endswith(".so") or ".so." in name:
                target = Path(extracted) / name.replace("/", "_")
                target.write_bytes(reader.extract(name))
                files.append(target)
        for path in files:
            dump = subprocess.run(["objdump", "-T", str(path)], capture_output=True, text=True).stdout
            for match in re.findall(r"GLIBC_(\d+(?:\.\d+)+)", dump):
                version = tuple(int(part) for part in match.split("."))
                if version > floor:
                    sys.exit(f"{executable}: {path.name} needs GLIBC_{match}, above {sys.argv[1]}")
                worst = max(worst, version)
print("Highest glibc symbol version required:", ".".join(map(str, worst)))
PY

tar -czf "$archive" -C dist agentic-discipline agentic
echo "Wrote $archive"
