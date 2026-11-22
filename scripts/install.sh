#!/usr/bin/env sh
# Install the Agentic Discipline CLIs, `agentic-discipline` and `agentic`, for this user.
#
#   curl -fsSL https://raw.githubusercontent.com/lreyesm1999/agentic-discipline-kit/main/scripts/install.sh | sh
#
# Linux x64: downloads the standalone build from the GitHub release, checks it against the
# release's SHA256SUMS and copies both executables to ~/.local/bin. No sudo, no Python.
# Anywhere else (macOS, ARM): installs the Python package from PyPI with uv or pipx.
# Nothing is installed when a download fails or a checksum does not match.
#
# Options are environment variables, because a piped script takes no arguments:
#   AGENTIC_DISCIPLINE_VERSION=2.1.0       a specific release instead of the latest
#   AGENTIC_DISCIPLINE_INSTALL_DIR=DIR     where the executables go (default ~/.local/bin)
#   AGENTIC_DISCIPLINE_RELEASES_URL=URL    a mirror laid out like .../releases (default GitHub)
#
# Uninstall:
#   curl -fsSL .../scripts/install.sh | sh -s -- --uninstall
set -eu

repo=lreyesm1999/agentic-discipline-kit
package=agentic-discipline-kit
commands="agentic-discipline agentic"
version=${AGENTIC_DISCIPLINE_VERSION:-}
version=${version#v}
bindir=${AGENTIC_DISCIPLINE_INSTALL_DIR:-${HOME}/.local/bin}
releases=${AGENTIC_DISCIPLINE_RELEASES_URL:-https://github.com/${repo}/releases}
releases=${releases%/}

say() { printf '%s\n' "$*"; }
fail() {
  printf 'agentic-discipline install: %s\n' "$*" >&2
  exit 1
}

usage() {
  say "Install the agentic-discipline and agentic commands for this user."
  say ""
  say "  sh install.sh                 install the latest release"
  say "  sh install.sh --uninstall     remove what this script installed"
  say ""
  say "Environment: AGENTIC_DISCIPLINE_VERSION, AGENTIC_DISCIPLINE_INSTALL_DIR,"
  say "AGENTIC_DISCIPLINE_RELEASES_URL. See the header of this script."
}

uninstall() {
  removed=""
  for command in $commands; do
    if [ -f "$bindir/$command" ]; then
      rm -f "$bindir/$command"
      say "Removed $bindir/$command"
      removed=1
    fi
  done
  [ -n "$removed" ] || say "Nothing to remove in $bindir."
  say "A copy installed with pip, pipx or uv is left alone: remove it with the same tool."
}

case "${1:-}" in
  "") ;;
  --uninstall)
    uninstall
    exit 0
    ;;
  -h | --help)
    usage
    exit 0
    ;;
  *) fail "unknown argument '$1' (try --help)" ;;
esac

fetch() { # url file
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 2 "$1" -o "$2"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "$2" "$1"
  else
    fail "downloading needs curl or wget"
  fi
}

sha256() { # file
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -c1-64
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | cut -c1-64
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$1" | sed 's/.*= *//'
  else
    fail "verifying the download needs sha256sum, shasum or openssl"
  fi
}

from_pypi() { # platform
  spec=$package
  [ -z "$version" ] || spec="$package==$version"
  say "There is no standalone build for $1; installing $spec from PyPI."
  if command -v uv >/dev/null 2>&1; then
    uv tool install --force "$spec"
  elif command -v pipx >/dev/null 2>&1; then
    pipx install --force "$spec"
  else
    fail "install uv (https://docs.astral.sh/uv/) or pipx, then run this again, or run: pipx install $spec"
  fi
  say "Next: cd your-repository && agentic-discipline init"
}

platform="$(uname -s)-$(uname -m)"
case "$platform" in
  Linux-x86_64 | Linux-amd64) asset=agentic-discipline-Linux-X64.tar.gz ;;
  MINGW* | MSYS* | CYGWIN*) fail "on Windows use scripts/install.ps1 from PowerShell" ;;
  *)
    from_pypi "$platform"
    exit 0
    ;;
esac

if [ -n "$version" ]; then
  base="$releases/download/v$version"
else
  base="$releases/latest/download"
fi

work=""
status=0
cleanup() { [ -z "$work" ] || rm -rf "$work"; }
trap 'status=$?; cleanup; exit $status' EXIT
trap 'cleanup; exit 130' INT TERM
work=$(mktemp -d "${TMPDIR:-/tmp}/agentic-discipline-install.XXXXXX")

say "Downloading $base/$asset"
fetch "$base/$asset" "$work/$asset" || fail "could not download $base/$asset"
fetch "$base/SHA256SUMS" "$work/SHA256SUMS" ||
  fail "could not download $base/SHA256SUMS; without it the download cannot be verified, so nothing was installed"

expected=$(awk -v name="$asset" '{ file = $2; sub(/^\*/, "", file) } file == name { print tolower($1); exit }' "$work/SHA256SUMS")
[ -n "$expected" ] || fail "SHA256SUMS has no line for $asset; nothing was installed"
actual=$(sha256 "$work/$asset")
[ "$actual" = "$expected" ] ||
  fail "checksum mismatch for $asset: expected $expected, got $actual; nothing was installed"
say "Checksum verified (SHA-256 $(printf %.16s "$actual")...)."

mkdir "$work/unpacked"
tar -xzf "$work/$asset" -C "$work/unpacked" || fail "could not unpack $asset"
for command in $commands; do
  [ -f "$work/unpacked/$command" ] || fail "$asset does not contain $command; nothing was installed"
done

mkdir -p "$bindir"
for command in $commands; do
  # Copy next to the target, then rename: replacing a running executable stays safe.
  cp "$work/unpacked/$command" "$bindir/.$command.new"
  chmod 755 "$bindir/.$command.new"
  mv -f "$bindir/.$command.new" "$bindir/$command"
done
for command in $commands; do
  "$bindir/$command" --version >/dev/null 2>&1 || fail "$bindir/$command was installed but does not run"
done

say "Installed $("$bindir/agentic-discipline" --version 2>&1 | head -n 1) to $bindir"
case ":${PATH}:" in
  *":$bindir:"*)
    found=$(command -v agentic-discipline || true)
    if [ -n "$found" ] && [ "$found" != "$bindir/agentic-discipline" ]; then
      say "Note: $found comes first on your PATH and will be used instead."
    fi
    ;;
  *)
    say "$bindir is not on your PATH. Add it, for example in ~/.profile:"
    say "  export PATH=\"$bindir:\$PATH\""
    ;;
esac
say "Next: cd your-repository && agentic-discipline init"
