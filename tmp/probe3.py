import re, sys
sys.path.insert(0, '.')
s = '走った。'
print([hex(ord(c)) for c in s])
print(repr(s[-1]))
print(bool(re.search(r"[ただ][。]$", s)))
print(bool(re.search(r"[ただ][。]\Z", s)))
