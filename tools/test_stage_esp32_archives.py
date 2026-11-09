#!/usr/bin/env python3
"""Test independent retries and validation of Arduino's archive cache."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from stage_esp32_archives import Archive, RETRY_DELAYS, archive_metadata, archives_for, github_assets, stage_archive


def metadata(name, payload, **fields):
    return dict(archiveFileName=name, url=f"https://example.com/{name}", size=str(len(payload)),
                checksum=f"SHA-256:{sha256(payload).hexdigest()}", **fields)


class ArchiveStagingTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.packages = self.root / "packages"
        self.packages.mkdir()
        pause = patch("stage_esp32_archives.time.sleep")
        self.sleep = pause.start()
        self.addCleanup(pause.stop)

    def test_pinned_linux_archives_and_cross_packager_tool(self):
        core = metadata("esp32-core.zip", b"core", version="3.3.8", architecture="esp32",
                        toolsDependencies=[dict(packager="esp32", name="esp-x32", version="2601"),
                                           dict(packager="arduino", name="dfu-util", version="0.11")])
        esp_tools = [dict(name="esp-x32", version="2601", systems=[
            metadata("xtensa-arm64.tar.gz", b"arm", host="aarch64-linux-gnu"),
            metadata("xtensa-x64.tar.gz", b"xtensa", host="x86_64-pc-linux-gnu")])]
        arduino_tools = [dict(name="dfu-util", version="0.11", systems=[
            metadata("dfu-linux.tar.gz", b"dfu", host="x86_64-linux-gnu")])]
        for filename, packager, platforms, tools in (
            ("package_esp32_index.json", "esp32", [dict(core, version="3.3.9"), core], esp_tools),
            ("package_index.json", "arduino", [], arduino_tools),
        ):
            (self.root / filename).write_text(json.dumps(dict(packages=[
                dict(name=packager, platforms=platforms, tools=tools)])), encoding="utf-8")
        self.assertEqual([archive.name for archive in archives_for(self.root, "3.3.8")],
                         ["esp32-core.zip", "xtensa-x64.tar.gz", "dfu-linux.tar.gz"])
        with self.assertRaisesRegex(ValueError, "has no esp32:esp32@3.3.7"):
            archives_for(self.root, "3.3.7")
        with self.assertRaises(ValueError):
            archive_metadata(metadata("../wrong.zip", b"x"))

    def test_each_archive_gets_its_own_attempts(self):
        bodies = {"xtensa.tar.gz": b"xtensa", "gdb.tar.gz": b"gdb", "riscv.tar.gz": b"riscv"}
        calls = Counter()

        def curl(command, check):
            name = command[-1].rsplit("/", 1)[1]
            partial = Path(command[command.index("--output") + 1])
            self.assertNotEqual(partial.parent, self.packages)
            self.assertIn("--location", command)
            self.assertNotIn("--head", command)
            self.assertFalse((self.packages / name).exists())
            calls[name] += 1
            if calls[name] <= 2:
                partial.write_bytes(b"HTTP 504")
                raise subprocess.CalledProcessError(22, command)
            partial.write_bytes(bodies[name])

        with patch("stage_esp32_archives.subprocess.run", side_effect=curl) as run:
            for name, body in bodies.items():
                stage_archive(archive_metadata(metadata(name, body)), self.packages)
            self.assertEqual(calls, dict.fromkeys(bodies, 3))
            self.assertEqual(run.call_count, 9)
        self.assertEqual(self.sleep.call_count, 6)
        self.assertEqual({path.name: path.read_bytes() for path in self.packages.iterdir()}, bodies)

    def test_verify_cache_and_replace_bad_download(self):
        archive = archive_metadata(metadata("core.zip", b"right"))
        destination = self.packages / archive.name
        destination.write_bytes(b"right")
        with patch("stage_esp32_archives.subprocess.run") as run:
            stage_archive(archive, self.packages)
        run.assert_not_called()
        destination.write_bytes(b"wrong")  # Same length, different SHA-256.

        def curl(command, check):
            partial = Path(command[command.index("--output") + 1])
            partial.write_bytes(b"wrong" if run.call_count == 1 else b"right")

        with patch("stage_esp32_archives.subprocess.run", side_effect=curl) as run:
            stage_archive(archive, self.packages)
            self.assertEqual(run.call_count, 2)
        self.assertEqual(destination.read_bytes(), b"right")

    def test_persistent_504_is_bounded_and_leaves_no_partial_cache(self):
        archive = Archive("unavailable.zip", "https://example.com/unavailable.zip", 5, sha256(b"right").hexdigest())
        with patch("stage_esp32_archives.subprocess.run", side_effect=subprocess.CalledProcessError(22, "curl")) as run:
            with self.assertRaisesRegex(ValueError, "unavailable.zip failed after 4 attempts"):
                stage_archive(archive, self.packages)
            self.assertEqual(run.call_count, len(RETRY_DELAYS) + 1)
        self.assertEqual(list(self.packages.iterdir()), [])
        self.assertEqual(list(self.root.glob(".hvp2p-download-*")), [])

    def test_github_release_504_uses_verified_api_asset(self):
        self.addCleanup(github_assets.cache_clear)
        repo = "https://github.com/espressif/binutils-gdb"
        api = "https://api.github.com/repos/espressif/binutils-gdb"
        tag, name, body = "esp-gdb-test", "gdb.tar.gz", b"compiler"
        archive = Archive(name, f"{repo}/releases/download/{tag}/{name}", len(body), sha256(body).hexdigest())
        urls = []

        def curl(command, **kwargs):
            url = command[-1]
            urls.append(url)
            if url == archive.url:
                raise subprocess.CalledProcessError(22, command)
            if url == f"{api}/releases/tags/{tag}":
                self.assertIn("Accept: application/vnd.github+json", command)
                doc = dict(assets=[dict(id=27, name=name, size=len(body), digest=f"sha256:{archive.digest}")])
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(doc).encode())
            self.assertEqual(url, f"{api}/releases/assets/27")
            self.assertIn("Accept: application/octet-stream", command)
            Path(command[command.index("--output") + 1]).write_bytes(body)

        with patch("stage_esp32_archives.subprocess.run", side_effect=curl):
            stage_archive(archive, self.packages)
        self.assertEqual(urls, [archive.url, f"{api}/releases/tags/{tag}", f"{api}/releases/assets/27"])
        self.assertEqual((self.packages / name).read_bytes(), body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
