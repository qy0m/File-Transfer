from datetime import datetime
from pathlib import Path
import shutil


root = Path(__file__).resolve().parent
backup = root / "var" / "setup-backups" / datetime.now().strftime(
    "%Y%m%d-%H%M%S-%f"
)

files = """
package.json
frontend/tsconfig.json
gateway/tsconfig.json
scripts/copy-bootstrap.mjs
frontend/includes/header.php
frontend/includes/footer.php
frontend/public/index.php
frontend/public/about.php
frontend/public/assets/css/styles.css
frontend/src/main.ts
gateway/src/server.ts
api/app/database.py
api/app/main.py
api/requirements.txt
frontend/Dockerfile
gateway/Dockerfile
api/Dockerfile
nginx/default.conf
compose.yaml
.env.example
.gitignore
.dockerignore
""".split()

changed = 0

for relative in files:
    path = root / relative

    if not path.is_file():
        print(f"Missing: {relative}")
        continue

    original = path.read_text(encoding="utf-8")
    wrappers = {
        f"cat > {relative} <<'EOF'",
        "EOF",
    }

    cleaned = "\n".join(
        line
        for line in original.splitlines()
        if line.strip() not in wrappers
    ) + "\n"

    if relative in (
        "frontend/tsconfig.json",
        "gateway/tsconfig.json",
    ):
        cleaned = cleaned.replace('"moduel"', '"module"')

    if cleaned == original:
        continue

    saved = backup / relative
    saved.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, saved)

    path.write_text(cleaned, encoding="utf-8")
    print(f"Fixed: {relative}")
    changed += 1

print(f"Updated {changed} file(s).")

if changed:
    print(f"Original files backed up to: {backup}")