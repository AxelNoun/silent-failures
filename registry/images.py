"""Render the README header and the link-preview image from entries.js.

Reads:  registry/entries.js (the twenty classes), registry/images/{tokens.css, header.html, social.html}
Writes: assets/registry-light.png, assets/registry-dark.png (README header, transparent background, 2x),
        assets/social-preview.png (1280 x 640, Open Graph image and repository social preview),
        assets/renders.json (SHA-256 of each image's rendered input).

PNG output is not byte-reproducible (font rasterisation varies), so the check compares inputs, not pixels:
`--check` rebuilds each input page and fails if its hash differs from assets/renders.json, i.e. if entries.js
or a template changed without the images being re-rendered. It needs Node.js, not Chrome.

Rendering needs Node.js (entries.js is a JavaScript literal, evaluated rather than re-parsed) and Google Chrome
or Chromium (set CHROME if it is not found). Fonts load from Google Fonts at render time; offline, Chrome falls
back to the system fonts listed in tokens.css.

    python registry/images.py           # re-render the images whose inputs changed
    python registry/images.py --force   # re-render all of them
    python registry/images.py --check   # CI: fail if an image is stale
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
TEMPLATES = HERE / "images"
ASSETS = ROOT / "assets"
HASHES = ASSETS / "renders.json"
CHROME_TIME_BUDGET_MS = 10000  # lets the web fonts load before the capture

# template, theme, output, CSS width, CSS height, device scale factor
RENDERS = [
    ("header.html", "light", ASSETS / "registry-light.png", 880, 258, 2),
    ("header.html", "dark", ASSETS / "registry-dark.png", 880, 258, 2),
    ("social.html", "light", ASSETS / "social-preview.png", 1280, 640, 1),
]


def load_registry():
    node = shutil.which("node")
    if node is None:
        sys.exit("Node.js not found: it is needed to read registry/entries.js.")
    script = (
        "const src=require('fs').readFileSync(0,'utf8');"
        "const {ENTRIES}=new Function(src+';return {ENTRIES};')();"
        "process.stdout.write(JSON.stringify(ENTRIES.map(e=>({id:e.id,family:e.family,detect:e.detect,en:e.en.name,fr:e.fr.name}))));"
    )
    src = (HERE / "entries.js").read_text(encoding="utf-8")
    out = subprocess.run([node, "-e", script], input=src, capture_output=True, text=True, encoding="utf-8", check=True)
    reg = json.loads(out.stdout)
    if not reg:
        sys.exit("entries.js has no entries.")
    return reg


def page(tpl, theme, registry):
    html = (TEMPLATES / tpl).read_text(encoding="utf-8")
    for marker in ("/*TOKENS*/", "/*DATA*/"):
        if html.count(marker) != 1:
            sys.exit(f"{tpl}: marker {marker} missing or repeated.")
    reg = json.dumps(registry, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tokens = (TEMPLATES / "tokens.css").read_text(encoding="utf-8")
    return html.replace("/*TOKENS*/", tokens).replace("/*DATA*/", f"const REG={reg};").replace("__THEME__", theme)


def find_chrome():
    for c in (os.environ.get("CHROME"),
              r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chrome")):
        if c and Path(c).exists():
            return c
    sys.exit("Chrome not found: set CHROME.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if an image's inputs changed since it was rendered")
    ap.add_argument("--force", action="store_true", help="re-render every image")
    args = ap.parse_args()

    registry = load_registry()
    recorded = json.loads(HASHES.read_text(encoding="utf-8")) if HASHES.exists() else {}
    hashes, stale = {}, []
    with tempfile.TemporaryDirectory() as tmp:
        chrome = None
        for tpl, theme, out, w, h, scale in RENDERS:
            html = page(tpl, theme, registry)
            key = out.name
            digest = hashlib.sha256(f"{w}x{h}@{scale}\n{html}".encode("utf-8")).hexdigest()
            hashes[key] = digest
            if recorded.get(key) == digest and out.exists() and not args.force:
                print(f"{out.relative_to(ROOT).as_posix()}: up to date")
                continue
            if args.check:
                stale.append(out.relative_to(ROOT).as_posix())
                continue
            chrome = chrome or find_chrome()
            src = Path(tmp) / f"{out.stem}.html"
            src.write_text(html, encoding="utf-8")
            out.parent.mkdir(parents=True, exist_ok=True)
            cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                   f"--user-data-dir={Path(tmp) / 'profile'}", f"--window-size={w},{h}",
                   f"--force-device-scale-factor={scale}", f"--virtual-time-budget={CHROME_TIME_BUDGET_MS}",
                   f"--screenshot={out}", src.as_uri()]
            if tpl == "header.html":
                cmd.insert(1, "--default-background-color=00000000")  # transparent, for GitHub light and dark
            subprocess.run(cmd, capture_output=True, check=True)
            if not out.exists() or out.stat().st_size == 0:
                sys.exit(f"empty capture: {out}")
            print(f"{out.relative_to(ROOT).as_posix()}: rendered ({out.stat().st_size // 1024} KB)")
    if args.check:
        if stale:
            print("stale images (run python registry/images.py and commit assets/): " + ", ".join(stale))
            return 1
        return 0
    HASHES.write_text(json.dumps(hashes, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
