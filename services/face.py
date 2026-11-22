"""Local, best-effort frontal face and eye detection using wheel-bundled cascades."""
from pathlib import Path
import cv2
import numpy as np
from PIL import ImageDraw

def detect(gray, cascade, minimum):
    path = Path(cv2.data.haarcascades) / f"haarcascade_{cascade}.xml"
    detector = cv2.CascadeClassifier(str(path))
    return detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=minimum)

def frontal_face(image):
    gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    faces = detect(gray, "frontalface_default", (45, 45))
    return (gray, faces[0]) if len(faces) == 1 else (gray, None)

def cover_reference(image):
    _, face = frontal_face(image)
    if face is None:
        raise ValueError("Face cover needs one detectable frontal face. Use the original or another photo.")
    x, y, w, h = map(int, face)
    image = image.copy()
    ImageDraw.Draw(image).ellipse((x+w*.12, y+h*.19, x+w*.88, y+h*.99), fill="#008080")
    return image

def visible_proportions(image):
    gray, face = frontal_face(image)
    if face is None:
        return None
    x, y, w, h = face
    eyes = detect(gray[y:y+int(h*.65), x:x+w], "eye", (12, 12))
    if len(eyes) != 2:
        return None
    left, right = sorted([(a+c/2, b+d/2) for a,b,c,d in eyes])
    spacing = (right[0]-left[0])/w
    if not .22 < spacing < .65 or abs(left[1]-right[1]) > h*.09:
        return None
    # Eye spacing relative to the detected face is a rough framing cue.
    return "open" if spacing >= .40 else "close"
