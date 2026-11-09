#!/usr/bin/env python3
"""Stage checked ESP32 core archives for Arduino CLI on the Linux x64 runner."""
import argparse
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import time
from urllib.parse import quote, unquote, urlsplit


LINUX_X64 = ("x86_64-pc-linux-gnu", "x86_64-linux-gnu")
RETRY_DELAYS = (5, 10, 20)
CURL = ("curl", "--disable", "--fail", "--silent", "--show-error", "--location",
        "--proto", "=https", "--proto-redir", "=https", "--connect-timeout", "20")


@dataclass(frozen=True)
class Archive:
    name: str
    url: str
    size: int
    digest: str


def archive_metadata(entry):
    name, url = entry["archiveFileName"], entry["url"]
    size, checksum = int(entry["size"]), entry["checksum"]
    parsed = urlsplit(url)
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", name) or
            parsed.scheme != "https" or not parsed.hostname or
            size <= 0 or not re.fullmatch(r"SHA-256:[0-9a-fA-F]{64}", checksum)):
        raise ValueError(f"Invalid package archive metadata for {name!r}")
    return Archive(name, url, size, checksum.split(":", 1)[1].lower())


def archives_for(data_dir, version):
    esp_index, arduino_index = (
        json.loads((data_dir / filename).read_text(encoding="utf-8"))["packages"]
        for filename in ("package_esp32_index.json", "package_index.json")
    )
    core = next((p for package in esp_index if package["name"] == "esp32"
                 for p in package["platforms"]
                 if p["architecture"] == "esp32" and p["version"] == version), None)
    if core is None:
        raise ValueError(f"Espressif package index has no esp32:esp32@{version}")
    tools = {}
    for package in (*esp_index, *arduino_index):
        for tool in package.get("tools", []):
            tools.setdefault((package["name"], tool["name"], tool["version"]), tool["systems"])

    archives = {}
    entries = [core]
    for tool in core["toolsDependencies"]:
        key = tool["packager"], tool["name"], tool["version"]
        systems = tools.get(key, [])
        system = next((s for host in LINUX_X64 for s in systems if s["host"] == host), None)
        if system is None:
            raise ValueError(f"No Linux x64 archive for {key[0]}:{key[1]}@{key[2]}")
        entries.append(system)
    for entry in entries:
        archive = archive_metadata(entry)
        if archive.name in archives and archive != archives[archive.name]:
            raise ValueError(f"Conflicting metadata for {archive.name}")
        archives[archive.name] = archive
    return list(archives.values())


def verified(path, archive):
    if not path.is_file() or path.stat().st_size != archive.size:
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == archive.digest


def github_release(url):
    parsed = urlsplit(url)
    if parsed.netloc != "github.com":
        return None
    match = re.fullmatch(r"/([\w.-]+/[\w.-]+)/releases/download/([^/]+)/([^/]+)", parsed.path, re.ASCII)
    if match is None:
        return None
    return f"https://api.github.com/repos/{match[1]}", quote(unquote(match[2]), safe=""), unquote(match[3])


@lru_cache(maxsize=32)
def github_assets(repository, tag):
    response = subprocess.run(
        [*CURL, "--max-time", "40", "--max-filesize", "2097152",
         "--header", "Accept: application/vnd.github+json", "--", f"{repository}/releases/tags/{tag}"],
        stdout=subprocess.PIPE, check=True,
    )
    return json.loads(response.stdout)["assets"]


def github_asset_url(archive, release):
    repository, tag, name = release
    asset = next((asset for asset in github_assets(repository, tag) if asset["name"] == name), None)
    if (asset is None or type(asset.get("id")) is not int or asset["size"] != archive.size or
            asset.get("digest") not in (None, f"sha256:{archive.digest}")):
        raise ValueError(f"GitHub API has no matching asset for {archive.name}")
    return f"{repository}/releases/assets/{asset['id']}"


def stage_archive(archive, packages):
    destination = packages / archive.name
    if verified(destination, archive):
        print(f"Verified cached archive {archive.name}", flush=True)
        return
    if destination.exists():
        destination.unlink()
    release = github_release(archive.url)
    # Curl transfers into a sibling scratch directory. Arduino CLI only sees
    # the archive after its length and SHA-256 match the index.
    with tempfile.TemporaryDirectory(prefix=".hvp2p-download-", dir=packages.parent) as directory:
        partial = Path(directory) / archive.name
        attempts = len(RETRY_DELAYS) + 1
        for attempt in range(1, attempts + 1):
            use_api = release is not None and attempt % 2 == 0
            route = "GitHub API" if use_api else "index URL"
            print(f"Downloading {archive.name} from {route} ({attempt}/{attempts})", flush=True)
            try:
                url = github_asset_url(archive, release) if use_api else archive.url
                headers = ["--header", "Accept: application/octet-stream"] if use_api else []
                subprocess.run(
                    [*CURL, *headers, "--max-filesize", str(archive.size),
                     "--max-time", "240", "--speed-time", "45", "--speed-limit", "16384",
                     "--output", str(partial), "--", url],
                    check=True,
                )
                if verified(partial, archive):
                    partial.replace(destination)
                    print(f"Verified downloaded archive {archive.name}", flush=True)
                    return
                reason = "length or SHA-256 mismatch"
            except subprocess.CalledProcessError as exc:
                reason = f"curl exited with code {exc.returncode}"
            except (KeyError, TypeError, ValueError) as exc:
                reason = f"GitHub asset metadata error ({exc})"
            partial.unlink(missing_ok=True)
            if attempt == attempts:
                raise ValueError(f"{archive.name} failed after {attempts} attempts ({reason})")
            print(f"::warning::{archive.name} attempt {attempt}/{attempts} failed ({reason}). Retrying.", flush=True)
            time.sleep(RETRY_DELAYS[attempt - 1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--downloads-dir", required=True, type=Path)
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        parser.error("This archive staging command requires the Linux x64 firmware runner")
    try:
        archives = archives_for(args.data_dir, args.version)
        packages = args.downloads_dir / "packages"
        packages.mkdir(parents=True, exist_ok=True)
        for archive in archives:
            stage_archive(archive, packages)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"ESP32 archive staging failed: {exc}") from exc
    print(f"Verified {len(archives)} archives for esp32:esp32@{args.version}", flush=True)


if __name__ == "__main__":
    main()
