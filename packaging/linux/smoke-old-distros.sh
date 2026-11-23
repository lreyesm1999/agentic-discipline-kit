#!/usr/bin/env bash
# Run the Linux standalone archive on the oldest distributions it claims to support.
#
#   bash packaging/linux/smoke-old-distros.sh agentic-discipline-Linux-X64.tar.gz
#
# Each image is a stock container plus git, which `agentic adopt` runs: the executables
# have to start with the C library that distribution ships, and create and query the
# FTS5 store.
set -euo pipefail

archive="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
images="${AGENTIC_SMOKE_IMAGES:-almalinux:8 debian:12 ubuntu:22.04}"

for image in $images; do
  echo "::group::$image"
  docker run --rm -v "$archive:/archive.tar.gz:ro" "$image" sh -ec '
    ldd --version 2>&1 | head -n 1
    if command -v apt-get >/dev/null; then
      apt-get update -qq && apt-get install -qq -y --no-install-recommends git >/dev/null
    else
      dnf install -q -y git-core >/dev/null
    fi
    mkdir /opt/agentic && tar -xzf /archive.tar.gz -C /opt/agentic
    cd /tmp
    /opt/agentic/agentic-discipline --version
    /opt/agentic/agentic --version
    mkdir control-smoke && echo "value = 1" > control-smoke/app.py
    /opt/agentic/agentic adopt control-smoke --json >/dev/null
    /opt/agentic/agentic --root control-smoke knowledge query app.py --json | grep -q "\"path\":\"app.py\""
  '
  echo "$image: OK"
  echo "::endgroup::"
done
