# pymss WebUI release assets

The 11 files listed in `provenance.json` are byte-for-byte copies of the
complete `pymss/server/webui_static/` subtree of the official **pymss 2.0.14**
wheel locked in the repository's `uv.lock`. The existing `index.html` already
matched that release. The bundle contains JavaScript (283775 bytes), CSS
(48095 bytes), and eight Noto Sans Variable WOFF2 subsets.

The wheel URL, SHA-256, archive prefix, and each file's SHA-256 are recorded
in `provenance.json`. Provenance and this README are local maintenance metadata,
not files from the wheel. The package's existing MIT notice is in
`../../LICENSE` (`tools/pymss/LICENSE`). The Noto Sans
copyright and SIL Open Font License are in `OFL.txt`; its copyright matches
the name-table metadata in all eight bundled fonts. The OFL text comes from
https://github.com/notofonts/latin-greek-cyrillic/blob/main/OFL.txt.

## Reproduce or verify the restoration

Obtain the exact wheel from `wheel_url` in `provenance.json` (or use a cached
copy), then run from the repository root with Python 3.12:

```sh
python tools/restore_pymss_webui.py /path/to/pymss-2.0.14-py3-none-any.whl
python tools/restore_pymss_webui.py /path/to/pymss-2.0.14-py3-none-any.whl --check
python -m unittest discover -s tests -p test_pymss_assets.py -v
```

The helper checks the wheel against both `uv.lock` and provenance, validates
the complete static file inventory and hashes, rejects unsafe archive paths,
and only then restores static files. It does not install the wheel or copy
any Python modules. The tests need FastAPI and httpx from the locked project
environment, and load only the static route module, without models or a GPU.

## Updating to another release

Update the locked pymss version first. Obtain that exact locked wheel and
verify its SHA-256. Review its HTML against the vendored server routes, then
update `provenance.json` with the new version, locked URL/hash, and the full
static subtree's per-file hashes. Run the helper, remove obsolete assets
listed only in the old manifest, and review any changed upstream notices.
Run the tests and the helper's `--check` mode before review. Use the release
wheel as the source; rebuilding mutable frontend sources is not reproducible.

`nix/package.nix` includes this entire subtree explicitly so fonts and notices
are retained alongside HTML, JavaScript, and CSS in the packaged source.
