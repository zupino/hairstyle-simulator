"""Read-only built-ins have negative IDs, leaving legacy SQLite IDs intact."""
from pathlib import Path
from backend import config, database

ASSETS = Path(__file__).resolve().parents[1] / "assets" / "hairstyles"
STYLES = [
    ("blunt-bob", "Blunt bob", "A clean jaw-length bob with a centre part."),
    ("curtain-lob", "Curtain lob", "Collarbone layers, parted fringe and soft waves."),
    ("curly-taper", "Curly taper", "Close graduated sides and defined curls on top."),
    ("textured-pixie", "Textured pixie", "Cropped nape with a textured side-swept fringe."),
]
BUILTINS = {
    -i: dict(id=-i, name=name, filename=slug+".jpg", description=brief,
             uploaded_by=None, created_at=None)
    for i, (slug, name, brief) in enumerate(STYLES, 1)
}

def get(style_id):
    return BUILTINS.get(style_id) if style_id < 0 else database.get_hairstyle(style_id)

def path(style, prepared=False):
    if style["id"] < 0:
        return ASSETS / style["filename"]
    original = Path(config.STORAGE_PATH) / style["filename"]
    covered = original.with_suffix(".covered.jpg")
    return covered if prepared and covered.exists() else original
