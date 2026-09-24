import os
import re
from pathlib import Path

backend_dir = Path("C:/Users/Guill/teamwork_projects/ai_culling_system/backend")

def search(pattern):
    print(f"--- Searching for {pattern} ---")
    regex = re.compile(pattern)
    for root, _, files in os.walk(backend_dir):
        if 'venv' in root or '__pycache__' in root or '.git' in root:
            continue
        for file in files:
            if not file.endswith('.py'):
                continue
            path = Path(root) / file
            try:
                content = path.read_text(encoding='utf-8')
                for i, line in enumerate(content.splitlines()):
                    if regex.search(line):
                        print(f"{path.relative_to(backend_dir)}:{i+1}: {line.strip()}")
            except Exception:
                pass

search(r'prefs\.get\(')
search(r'settings\.get\(')
search(r'ratings_map')
search(r'preset')
search(r'color')
search(r'router\.get\(".*health"\)')
search(r'router\.get\(".*status"\)')
search(r'router\.get\(".*log"\)')
