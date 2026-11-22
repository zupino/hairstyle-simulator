"""Turn consultation choices into editable, hair-only briefs."""
from typing import Literal
from pydantic import BaseModel, Field
from services.face import visible_proportions

class Preferences(BaseModel):
    length: Literal["unsure", "preserve", "tie", "short"] = "unsure"
    effect: Literal["unsure", "elongate", "fullness", "polished", "bold"] = "unsure"
    effort: Literal["easy", "styled"] = "easy"
    forehead_clear: bool = False
    note: str = Field(default="", max_length=200)

EFFECTS = {
    "elongate": ("elongate", "slim", "leaner"),
    "fullness": ("fuller", "fatter", "volume"),
    "polished": ("polished", "serious", "structured"),
    "bold": ("bold", "extreme", "edgy"),
}
DETAILS = {
    "elongate": "Keep the sides quiet and place the visual lift at the crown.",
    "fullness": "Place soft width around the cheeks through layered sides.",
    "polished": "Define the perimeter with a clean, continuous line.",
    "bold": "Give the silhouette an asymmetric outline.",
}

def suggest(image, prefs):
    cue = visible_proportions(image)
    effect = prefs.effect
    if effect == "unsure":
        effect = next((key for key, words in EFFECTS.items()
                       if any(word in prefs.note.lower() for word in words)), "unsure")
    shapes = {
        "short": [("Tapered crop", "Taper the nape and sides with textured length on top."),
                  ("Soft short layers", "Use rounded short layers with a soft graduated nape.")],
        "tie": [("Long face-framing layers", "Keep enough length throughout for a ponytail. Start layers below the chin."),
                ("Full ponytail perimeter", "Keep a full, even perimeter and leave the front long enough to tie back.")],
    }
    candidates = shapes.get(prefs.length, [
        ("Soft framing layers", "Retain the existing length and add subtle framing layers."),
        ("Defined outline", "Keep the existing length and refine the perimeter with minimal layering.")])
    if cue == "close" and effect == "unsure":
        candidates = list(reversed(candidates))
    results = []
    for name, shape in candidates:
        details = [shape, "Work with the existing natural texture."]
        if effect in DETAILS:
            details.append(DETAILS[effect])
        if prefs.forehead_clear:
            details.append("Keep the hair parted away from the forehead without bangs.")
        details.append("Use an air-dry finish." if prefs.effort == "easy" else "Allow a styled finish with a round brush or diffuser.")
        if prefs.note:
            details.append("Customer preference, within the length and fringe constraints: " + prefs.note)
        results.append({"name": name, "brief": " ".join(details)})
    observation = {
        "open": "The eye landmarks appear relatively wide within the detected face. Soft framing is one option.",
        "close": "The eye landmarks appear relatively central within the detected face. A defined outline is one option.",
        None: "No reliable frontal eye pair detected. These ideas use your preferences.",
    }[cue]
    return {"observation": observation, "options": results}
