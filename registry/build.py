"""Build index.html from template.html + entries.js (inlined at /*ENTRIES*/).

template.html is a page fragment (the form the claude.ai artifact takes). For GitHub Pages, index.html
wraps it in a full document: doctype, and a <head> that receives the <!--pages-head--> block (charset,
viewport, link-preview tags), so the page renders in standards mode and at device width on phones.
`--fragment PATH` also writes the bare fragment, without that block, for publishing as an artifact.
Output is written with LF line endings on every platform, so the CI comparison holds on Windows too.
"""
import argparse
from pathlib import Path

here = Path(__file__).parent
ap = argparse.ArgumentParser()
ap.add_argument("--fragment", type=Path, help="also write the bare fragment (artifact form) to this path")
args = ap.parse_args()

tpl = (here / "template.html").read_text(encoding="utf-8")
ent = (here / "entries.js").read_text(encoding="utf-8")
assert tpl.count("/*ENTRIES*/") == 1
page = tpl.replace("/*ENTRIES*/", ent)

HEAD_A, HEAD_B, BODY = "<!--pages-head-->", "<!--/pages-head-->", "<!--body-->"
assert page.count(HEAD_A) == 1 and page.count(HEAD_B) == 1 and page.count(BODY) == 1
i, j = page.index(HEAD_A), page.index(HEAD_B)
pages_head = page[i + len(HEAD_A):j].strip("\n")
fragment = page[:i] + page[j + len(HEAD_B):].lstrip("\n")
head, body = fragment.split(BODY)

doc = (
    '<!doctype html>\n<html lang="en">\n<head>\n'
    + pages_head + "\n" + head.strip("\n") + "\n</head>\n<body>\n"
    + body.strip("\n") + "\n</body>\n</html>\n"
)
(here.parent / "index.html").write_text(doc, encoding="utf-8", newline="\n")
print("wrote index.html")
if args.fragment:
    args.fragment.write_text(fragment.replace(BODY + "\n", ""), encoding="utf-8", newline="\n")
    print(f"wrote {args.fragment}")
