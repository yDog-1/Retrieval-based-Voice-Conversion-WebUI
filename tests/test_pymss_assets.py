"""Release-bundle integrity and real HTTP responses, without inference imports."""

import hashlib
from html.parser import HTMLParser
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib
import unittest
from urllib.parse import unquote, urljoin, urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "tools/pymss/server/webui_static"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


webui = load_module("pymss_static_routes", STATIC.parent / "webui.py")
restore = load_module("restore_pymss_webui", ROOT / "tools/restore_pymss_webui.py")


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        self.urls.extend(value for key, value in attrs if key in {"src", "href"} and value)


class PymssAssetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((STATIC / "provenance.json").read_text())
        cls.lock = tomllib.loads((ROOT / "uv.lock").read_text())

    def test_manifest_matches_lock_and_complete_bundle(self):
        package = next(p for p in self.lock["package"] if p["name"] == "pymss")
        self.assertEqual(package["version"], self.manifest["version"])
        self.assertTrue(any(
            w["url"] == self.manifest["wheel_url"]
            and w["hash"] == "sha256:" + self.manifest["wheel_sha256"]
            for w in package["wheels"]
        ))
        actual = {"index.html"} | {
            p.relative_to(STATIC).as_posix() for p in (STATIC / "assets").rglob("*")
            if p.is_file()
        }
        self.assertEqual(actual, set(self.manifest["files"]))
        for name, digest in self.manifest["files"].items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((STATIC / name).read_bytes()).hexdigest(), digest)
        fonts = list((STATIC / "assets").glob("*.woff2"))
        self.assertEqual(len(fonts), 8)
        for font in fonts:
            self.assertEqual(font.read_bytes()[:4], b"wOF2")
        self.assertIn("SIL OPEN FONT LICENSE Version 1.1", (STATIC / "OFL.txt").read_text())

    def test_html_css_references_and_http_routes(self):
        app = FastAPI()
        webui.register_webui_routes(app)
        parser = References()
        parser.feed((STATIC / "index.html").read_text())
        self.assertEqual(len(parser.urls), 2)
        pending = [("/ui/", url) for url in parser.urls]
        visited = set()
        with TestClient(app) as client:
            redirect = client.get("/ui", follow_redirects=False)
            self.assertEqual(redirect.status_code, 307)
            self.assertEqual(redirect.headers["location"], "/ui/")
            for url in ("/ui/", "/ui/models/example"):
                response = client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.content, (STATIC / "index.html").read_bytes())
                self.assertIn("text/html", response.headers["content-type"])
            while pending:
                base, reference = pending.pop()
                url = urlsplit(urljoin(base, reference))
                if url.scheme or url.netloc or not url.path or reference.startswith("#"):
                    continue
                path = unquote(url.path)
                if path in visited:
                    continue
                visited.add(path)
                with self.subTest(url=path):
                    self.assertTrue(path.startswith("/ui/assets/"))
                    local = STATIC / path.removeprefix("/ui/")
                    self.assertTrue(local.is_file(), path)
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.content, local.read_bytes())
                    suffix = local.suffix
                    if suffix == ".css":
                        self.assertIn("text/css", response.headers["content-type"])
                        pending.extend((path, ref.strip(" \"'")) for ref in re.findall(
                            r"url\(([^)]+)\)", response.text
                        ))
                    elif suffix == ".js":
                        self.assertIn("javascript", response.headers["content-type"])
                    elif suffix == ".woff2":
                        self.assertIn("font/woff2", response.headers["content-type"])
            self.assertEqual(len(visited), 10)  # JS + CSS + all eight CSS font URLs
            for path in ("missing.js", "%2e%2e/index.html", "%2e%2e/%2e%2e/webui.py"):
                with self.subTest(missing_or_traversal=path):
                    self.assertEqual(client.get("/ui/assets/" + path).status_code, 404)

    def test_missing_index_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = FastAPI()
            webui.register_webui_routes(app, root / "static")
            (root / "static/assets").mkdir(parents=True)
            (root / "secret.txt").write_text("outside static subtree")
            (root / "static/assets/escape.txt").symlink_to(root / "secret.txt")
            with TestClient(app) as client:
                response = client.get("/ui/")
                self.assertEqual(response.status_code, 500)
                self.assertEqual(response.json()["error"]["code"], "webui_assets_missing")
                self.assertEqual(client.get("/ui/assets/escape.txt").status_code, 404)

    def test_restore_rejects_wrong_wheel_and_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "wrong.whl"
            wheel.write_bytes(b"not the locked wheel")
            with self.assertRaisesRegex(ValueError, "Wheel SHA-256"):
                restore.verified_payload(wheel, self.manifest, self.lock)
            with self.assertRaisesRegex(ValueError, "does not match uv.lock"):
                restore.verified_payload(wheel, {**self.manifest, "version": "0"}, self.lock)

    @unittest.skipUnless(os.environ.get("PYMSS_PACKAGED_SOURCE"), "Set PYMSS_PACKAGED_SOURCE to Nix app.src")
    def test_packaged_source_has_bundle_and_notices(self):
        source = Path(os.environ["PYMSS_PACKAGED_SOURCE"])
        packaged = source / "tools/pymss/server/webui_static"
        for local in STATIC.rglob("*"):
            if local.is_file():
                with self.subTest(file=local.name):
                    self.assertEqual((packaged / local.relative_to(STATIC)).read_bytes(), local.read_bytes())
        self.assertEqual((source / "tools/pymss/LICENSE").read_bytes(), (ROOT / "tools/pymss/LICENSE").read_bytes())


if __name__ == "__main__":
    unittest.main()
