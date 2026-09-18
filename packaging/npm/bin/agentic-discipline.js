#!/usr/bin/env node
"use strict";

/**
 * Zero-install launcher: `npx agentic-discipline init`.
 *
 * Resolves a real CLI in this order, so the common case needs no network and
 * no Python:
 *   1. an `agentic-discipline` already on PATH;
 *   2. a standalone build cached from a previous run;
 *   3. the standalone build for this platform, downloaded from the GitHub
 *      release that matches this package version.
 */

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pipeline } = require("node:stream/promises");
const { createGunzip } = require("node:zlib");

const REPOSITORY = "lreyesm1999/agentic-discipline-kit";
const VERSION = require("../package.json").version;
const IS_WINDOWS = process.platform === "win32";
const BINARY = IS_WINDOWS ? "agentic-discipline.exe" : "agentic-discipline";

// Only the builds the release workflow produces. Anywhere else, the launcher
// explains how to install the Python CLI instead of requesting a missing asset.
const ASSETS = {
  "win32-x64": `agentic-discipline-Windows-X64.zip`,
  "linux-x64": `agentic-discipline-Linux-X64.tar.gz`,
};

function cacheDirectory() {
  const base =
    process.env.AGENTIC_DISCIPLINE_CACHE ||
    path.join(os.homedir(), ".cache", "agentic-discipline");
  return path.join(base, VERSION);
}

function onPath() {
  const probe = spawnSync(BINARY, ["--version"], { stdio: "ignore" });
  return probe.status === 0 ? BINARY : null;
}

function cached() {
  const candidate = path.join(cacheDirectory(), BINARY);
  return fs.existsSync(candidate) ? candidate : null;
}

async function download() {
  const key = `${process.platform}-${process.arch}`;
  const asset = ASSETS[key];
  if (!asset) {
    throw new Error(
      `no standalone build for ${key}. Install the CLI with ` +
        `"pipx install agentic-discipline-kit" instead.`
    );
  }
  const url = `https://github.com/${REPOSITORY}/releases/download/v${VERSION}/${asset}`;
  process.stderr.write(`Fetching agentic-discipline ${VERSION} for ${key}...\n`);

  const response = await fetch(url, { redirect: "follow" });
  if (!response.ok) {
    throw new Error(
      `download failed (${response.status}) from ${url}. ` +
        `Install the CLI with "pipx install agentic-discipline-kit" instead.`
    );
  }

  const directory = cacheDirectory();
  fs.mkdirSync(directory, { recursive: true });
  const archive = path.join(directory, asset);
  await pipeline(response.body, fs.createWriteStream(archive));

  if (asset.endsWith(".zip")) {
    // tar ships with Windows 10+ and handles zip archives.
    run("tar", ["-xf", archive, "-C", directory]);
  } else {
    const tarball = archive.replace(/\.gz$/, "");
    await pipeline(
      fs.createReadStream(archive),
      createGunzip(),
      fs.createWriteStream(tarball)
    );
    run("tar", ["-xf", tarball, "-C", directory]);
    fs.rmSync(tarball, { force: true });
  }
  fs.rmSync(archive, { force: true });

  const binary = path.join(directory, BINARY);
  if (!fs.existsSync(binary)) {
    throw new Error(`archive ${asset} did not contain ${BINARY}`);
  }
  if (!IS_WINDOWS) {
    fs.chmodSync(binary, 0o755);
  }
  return binary;
}

function run(command, args) {
  const result = spawnSync(command, args, { stdio: "inherit" });
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} failed`);
  }
}

async function main() {
  let binary = onPath() || cached();
  if (!binary) {
    binary = await download();
  }
  const result = spawnSync(binary, process.argv.slice(2), { stdio: "inherit" });
  process.exit(result.status === null ? 1 : result.status);
}

main().catch((error) => {
  process.stderr.write(`agentic-discipline: ${error.message}\n`);
  process.exit(1);
});
