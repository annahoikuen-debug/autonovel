import pathlib,re,unicodedata
targets=[]
for p in list(pathlib.Path(".").rglob("*.py"))+list(pathlib.Path(".").rglob("*.md"))+list(pathlib.Path(".").rglob("*.ts"))+list(pathlib.Path(".").rglob("*.tsx")):
    s=str(p)
    if any(x in s for x in (".venv","node_modules",".git/","archive/","tmp/",".mypy_cache",".ruff_cache",".hypothesis","chroma_db","storage/","output/","logs/","data/","artifacts/")): continue
    targets.append(p)
# 1) CJK に直接 연결された欧文（ocrude 等の混入）
pat=re.compile(r"[\u3040-\u30ff\u4e00-\u9fff][A-Za-z]{2,}|[A-Za-z]{2,}[\u3040-\u30ff\u4e00-\u9fff]")
hits=[]
for p in targets:
    try: t=p.read_text(encoding="utf-8")
    except Exception: continue
    for i,line in enumerate(t.splitlines(),1):
        for m in pat.finditer(line):
            hits.append((str(p),i,m.group(),line.strip()[:110]))
print(f"=== CJK+latin 混在: {len(hits)} ===")
for h in hits[:60]: print(f"  {h[0]}:{h[1]}  [{h[2]}]  {h[3]}")
