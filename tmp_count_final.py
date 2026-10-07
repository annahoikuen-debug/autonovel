import io, re, sys, collections

path = sys.argv[1] if len(sys.argv) > 1 else "reports/qa_final_run4.txt"
with io.open(path, encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

r = collections.Counter()
for l in lines:
    if re.search(r"\[\s*\d+%\]$", l):
        # ドット列 + 状態文字を数える
        m = re.match(r"^(\.*)", l)
        r["."] += len(m.group(1)) if m else 0
        for ch in re.findall(r"[sFEx]", l):
            r[ch] += 1

total = sum(r.values())
print("progress-char total (approx tests executed):", total)
for k in (".", "s", "F", "E", "x"):
    print(f"  {k}: {r[k]}")
