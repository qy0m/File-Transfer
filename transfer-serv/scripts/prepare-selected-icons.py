from copy import deepcopy
from datetime import datetime
from pathlib import Path
import shutil
import urllib.request
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
icons_dir = root / "frontend/public/assets/icons"

lucide_base = "https://cdn.jsdelivr.net/npm/lucide-static@0.468.0/"
tabler_base = "https://cdn.jsdelivr.net/gh/tabler/tabler-icons@v3.31.0/"

choices = {
    "cloud-arrow-up": "upload",
    "folder-plus": "folder-plus",
    "collection": "folders",
    "sliders": "settings",
    "person-lock": "user-round",
    "exclamation-circle": "triangle-alert",
    "cloud-arrow-down": "download",
    "shield-lock": "lock-keyhole",
    "person-check": "user-round-check",
    "incognito": "user-round",
    "hourglass-split": "hourglass",
    "link-45deg": "link",
    "github": "code-xml",
}

def download(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Filevoya-icon-setup/1.0"},
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(1_048_577)

    if not data or len(data) > 1_048_576:
        raise RuntimeError(f"Invalid download: {url}")

    return data

licenses = {
    "lucide-LICENSE.txt": download(lucide_base + "LICENSE"),
    "feather-LICENSE.txt": download(
        "https://cdn.jsdelivr.net/gh/feathericons/feather@v4.29.2/LICENSE"
    ),
    "tabler-LICENSE.txt": download(tabler_base + "LICENSE"),
}

sources = {}

for name in sorted(set(choices.values())):
    sources[name] = ET.fromstring(
        download(lucide_base + "icons/" + name + ".svg")
    )
    print(f"Downloaded Lucide: {name}")

sources["tabler-server-2"] = ET.fromstring(
    download(tabler_base + "icons/outline/server-2.svg")
)
choices["hdd"] = "tabler-server-2"

namespace = "http://www.w3.org/2000/svg"
ET.register_namespace("", namespace)

sprite = ET.Element(f"{{{namespace}}}svg")
metadata = ET.SubElement(sprite, f"{{{namespace}}}metadata")

metadata.text = "\n\n".join(
    name + "\n" + data.decode("utf-8")
    for name, data in licenses.items()
)

allowed_tags = {
    "svg",
    "path",
    "line",
    "polyline",
    "polygon",
    "rect",
    "circle",
    "ellipse",
    "g",
}

for symbol_id, source_name in choices.items():
    source = sources[source_name]

    if source.tag != f"{{{namespace}}}svg":
        raise RuntimeError(f"Invalid SVG: {source_name}")

    for node in source.iter():
        if node.tag.split("}")[-1] not in allowed_tags:
            raise RuntimeError(
                f"Unexpected SVG element: {source_name}"
            )

        for key, value in node.attrib.items():
            if (
                key.lower().startswith("on")
                or key.split("}")[-1] == "href"
                or "url(" in value.lower()
            ):
                raise RuntimeError(
                    f"Unexpected SVG attribute: {source_name}"
                )

    attributes = {
        key: value
        for key, value in source.attrib.items()
        if key not in {"width", "heigt", "class", "id"}
    }

    attributes["id"] = symbol_id

    symbol = ET.SubElement(
        sprite,
        f"{{{namespace}}}symbol",
        attributes,
    )

    for child in source:
        symbol.append(deepcopy(child))

sprite_data = ET.tostring(
    sprite,
    encoding="utf-8",
    xml_declaration=True,
)

ET.fromstring(sprite_data)

outputs = {
    icons_dir / "filevoya-icons.svg": sprite_data,
}

outputs.update({
    icons_dir / name: data
    for name, data in licenses.items()
})

existing = [path for path in outputs if path.exists()]

if existing:
    backup = Path.home() / "Backups" / (
        "filevoya-before-selected-icons-"
        + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    )

    backup.mkdir(parents=True, mode=0o700)

    for path in existing:
        shutil.copy2(path, backup / path.name)

    print(f"Previous icon assets saved to: {backup}")

icons_dir.mkdir(parents=True, exist_ok=True)


for path, data in outputs.items():
    path.write_bytes(data)

print(
    f"Prepared {len(choices)} icon symbols, "
    "including Tabler server 2 for storage."
)
print(
    "License notices are included in the sprite "
    "and separate text files."
)
print(
    "Next: update the two PHP icon helpers, "
    "then rebuild php and web."
)