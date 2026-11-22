# Hairstyle simulator

A salon operator can photograph or upload a selfie, try a catalogue cut or explore two suggested cuts, choose a colour and compare previews. The original selfie is sent to Black Forest Labs for each render. Selfies and generated results are held in browser memory for the session. Start a new session between customers.

## Run locally

Use Python 3.12. Set BFL_API_KEY, SECRET_KEY and optionally ADMIN_PASSWORD in the shell before starting.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn backend.main:app --port 8080
```

Open http://localhost:8080/ for the operator and /admin/ for catalogue and operator management. Both accept the bootstrapped admin login. Camera capture requires HTTPS or localhost. File upload also works without camera access.

## Cloud Run demo

Deploy from source with the included Dockerfile from the repository root. It selects CPython 3.12 on Debian and installs binary wheels only. The Procfile supplies the equivalent service command for a buildpack deployment. Store the three secrets in Secret Manager and grant the runtime service account access. Example using existing secrets named bfl-api-key, salon-jwt and salon-admin:

```sh
gcloud run deploy hairstyle-simulator --source . --region europe-west3 \
  --min-instances 0 --max-instances 1 --allow-unauthenticated \
  --set-secrets BFL_API_KEY=bfl-api-key:latest,SECRET_KEY=salon-jwt:latest,ADMIN_PASSWORD=salon-admin:latest
```

The service is publicly reachable, with app login protecting salon APIs. The demo uses per-instance SQLite and files. Cold starts restore the four bundled styles and bootstrap admin. Added references, operators and pending jobs can disappear on instance replacement. Keep the demo at one instance to limit cross-instance state mismatches; durable multi-instance operation would require shared storage.

| Setting | Use |
| --- | --- |
| BFL_API_KEY | Required BFL credential |
| SECRET_KEY | Required JWT signing secret; generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| BFL_MODEL | Default `flux-2-pro`; also `flux-2-max` and `flux-3-image` |
| ADMIN_PASSWORD | Optional cold-start admin bootstrap, minimum 8 characters. Existing accounts are untouched |
| ADMIN_USERNAME | Bootstrap username, default `admin` |
| DB_PATH | SQLite path, default `./hairstyle_simulator.db` |
| STORAGE_PATH | Additional uploads, default `./storage/hairstyles` |
| ACCESS_TOKEN_TTL | Login lifetime in seconds, default 3600 |
| PORT | Cloud Run supplies the listening port; local container default 8080 |

For manual bootstrap use `python scripts/create_admin.py --username admin --password …`. Existing SQLite catalogue IDs and legacy bcrypt passwords remain usable.

## Salon workflows

**Try a style.** Select a built-in or uploaded reference. Admins can preview a face cover before uploading. The gallery displays the original, while rendering uses the prepared copy. Covering the reference face is experimental. Compare repeated renders with the same selfie, cut and colour to evaluate identity and haircut accuracy separately.

**Suggest a cut.** A local frontal-face and eye detector supplies a rough framing cue when one frontal face and two consistent eye detections are available. Customer preferences determine the briefs. Missing landmarks fall back to preference-only ideas. The operator chooses and can edit a brief before the first billed generation. A front selfie cannot establish density, growth patterns or real-world suitability.

**Colour.** Keep the selfie colour, select a shade or enter a custom shade. Matching the reference colour is available in catalogue mode. Pin up to two results beside the original for discussion.

The four generated mannequin photographs under assets/hairstyles ship with every instance. No runtime image download or database seeding is required. The app uses wheel-bundled OpenCV cascades and has no MediaPipe model download or compiler requirement.

[BFL image editor API](https://docs.bfl.ml/api-reference/utility/generate-an-image-with-flux-3)
