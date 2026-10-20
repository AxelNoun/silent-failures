"""Build index.html from template.html + entries.js (inlined at /*ENTRIES*/)."""
from pathlib import Path
here = Path(__file__).parent
tpl = (here / "template.html").read_text(encoding="utf-8")
ent = (here / "entries.js").read_text(encoding="utf-8")
assert tpl.count("/*ENTRIES*/") == 1
(here.parent / "index.html").write_text(tpl.replace("/*ENTRIES*/", ent), encoding="utf-8")
print("wrote index.html")
