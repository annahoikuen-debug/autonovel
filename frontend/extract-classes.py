#!/usr/bin/env python3
import re
from pathlib import Path

src_dir = Path(__file__).parent / 'src'
output_file = Path(__file__).parent / 'plans' / 'tailwind-raw.txt'

class_names = set()

# Pattern to match className="..." and className={`...`}
pattern_static = re.compile(r'className="([^"]*)"')
pattern_template = re.compile(r'className=`([^`]+)`')

for tsx_file in src_dir.rglob('*.tsx'):
    try:
        content = tsx_file.read_text(encoding='utf-8')
        # Static className
        for match in pattern_static.findall(content):
            if match.strip():
                class_names.add(match.strip())
        # Template literal className
        for match in pattern_template.findall(content):
            if match.strip():
                class_names.add(match.strip())
    except Exception as e:
        print(f"Error reading {tsx_file}: {e}")

# Write sorted unique class names
sorted_names = sorted(class_names)
output_file.write_text('\n'.join(sorted_names), encoding='utf-8')
print(f"Extracted {len(sorted_names)} unique class names to {output_file}")
