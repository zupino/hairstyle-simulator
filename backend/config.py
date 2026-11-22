"""Runtime settings for the salon service."""
import os

def credential(name):
    """Prefer the Cloud Run literal, with the original name supported locally."""
    return os.getenv(f"SALON_{name}", os.getenv(name, ""))


BFL_API_KEY = credential("BFL_API_KEY")
BFL_MODEL = os.getenv("BFL_MODEL", "flux-2-pro")
BFL_API_BASE = "https://api.bfl.ai/v1"
MODELS = ("flux-2-pro", "flux-2-max", "flux-3-image")
SECRET_KEY = credential("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = int(os.getenv("ACCESS_TOKEN_TTL", "3600"))
STORAGE_PATH = os.getenv("STORAGE_PATH", "./storage/hairstyles")
DB_PATH = os.getenv("DB_PATH", "./hairstyle_simulator.db")
