"""Regression checks for cold starts, model-specific payloads and the two workflows."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend import config
from backend.main import app
from services import catalogue
from services.bfl import payload


class SalonWorkflows(unittest.TestCase):
    def setUp(self):
        temp = self.enterContext(tempfile.TemporaryDirectory())
        for name, value in {
            "DB_PATH": temp + "/salon.db", "STORAGE_PATH": temp + "/uploads",
            "SECRET_KEY": "test-only" * 5, "BFL_API_KEY": "mock",
        }.items():
            self.enterContext(patch.object(config, name, value))
        self.enterContext(patch.dict(os.environ, ADMIN_PASSWORD="test-password", ADMIN_USERNAME="admin"))
        self.client = self.enterContext(TestClient(app))
        login = self.client.post("/api/auth/token", data={"username": "admin", "password": "test-password"})
        self.client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        self.image = (catalogue.ASSETS / "blunt-bob.jpg").read_bytes()
        self.photo = {"selfie": ("selfie.jpg", self.image, "image/jpeg")}

    def test_catalogue_after_db_replacement(self):
        self.assertEqual(len(self.client.get("/api/hairstyles").json()), 4)
        Path(config.DB_PATH).unlink()
        with TestClient(app) as restarted:
            self.assertEqual(self.client.get("/api/hairstyles").status_code, 401)
            token = restarted.post("/api/auth/token", data={"username": "admin", "password": "test-password"}).json()
            restarted.headers["Authorization"] = "Bearer " + token["access_token"]
            self.assertEqual(restarted.get("/api/hairstyles/-1/image").content, self.image)

    def test_reference_and_consultation_input_roles(self):
        ideas = self.client.post("/api/generate/suggest", files=self.photo,
                                 data={"preferences": '{"length":"tie","effect":"fullness"}'}).json()
        self.assertEqual(len(ideas["options"]), 2)
        self.assertIn("ponytail", ideas["options"][0]["brief"])
        submit = AsyncMock(return_value={"id": "example", "polling_url": "https://example.invalid"})
        with patch("backend.routes.generation.submit_generation", submit):
            for form in ({"hairstyle_id": -1}, {"mode": "suggest", "cut": ideas["options"][0]["brief"]}):
                response = self.client.post("/api/generate", files=self.photo, data={**form, "colour": "Copper"})
                self.assertEqual(response.status_code, 202)
                selfie, reference, brief, colour = submit.await_args.args
                self.assertEqual(reference is not None, "hairstyle_id" in form)
                for model in config.MODELS:
                    body = payload(model, selfie, reference, brief, colour)
                    self.assertIn("Copper", body["prompt"])
                    if model == "flux-3-image":
                        self.assertEqual(body["images"], [selfie, reference] if reference else [selfie])
                    else:
                        self.assertEqual(body.get("input_image_2"), reference)
                        self.assertEqual(body["input_image"], selfie)
