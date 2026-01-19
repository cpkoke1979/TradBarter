from pathlib import Path
import re

TEMPLATES_DIR = Path("templates")

def fix_links(content):
    # Convert href="about.html" -> href="/about"
    content = re.sub(r'href="index\.html"', 'href="/"', content)
    content = re.sub(r'href="([a-zA-Z0-9_-]+)\.html"', r'href="/\1"', content)

    # Fix account mode querystrings
    content = re.sub(r'href="/account\.html\?mode=', 'href="/account?mode=', content)

    # Fix anchors like index.html#section
    content = re.sub(r'href="index\.html#', 'href="/#', content)

    # Fix static paths
    content = re.sub(r'src="static/', 'src="/static/', content)
    content = re.sub(r'href="static/', 'href="/static/', content)

    # Normalise brand/social folders to img
    content = content.replace("/static/brand/", "/static/img/")
    content = content.replace("/static/social/", "/static/img/")

    return content


for template in TEMPLATES_DIR.glob("*.html"):
    original = template.read_text(encoding="utf-8")
    backup = template.with_suffix(template.suffix + ".bak")

    backup.write_text(original, encoding="utf-8")

    updated = fix_links(original)
    template.write_text(updated, encoding="utf-8")

    print(f"Updated: {template.name}")

print("\nDone. Backups saved as .bak files.")
