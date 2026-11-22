# Hairstyle simulator

A salon operator can photograph or upload a selfie, try a catalogue cut or explore two suggested cuts, choose a colour and compare previews. The original selfie is sent to Black Forest Labs for each render. Selfies and generated results are held in browser memory for the session. Start a new session between customers.

## Run locally

Use Python 3.13. Set BFL_API_KEY, SECRET_KEY and optionally ADMIN_PASSWORD in the shell before starting.

```sh
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn backend.main:app --port 8080
```

Open http://localhost:8080/ for the operator and /admin/ for catalogue and operator management. Both accept the bootstrapped admin login. Camera capture requires HTTPS or localhost. File upload also works without camera access.

## Cloud Run demo

Deploy from the repository root using Google Cloud buildpacks. The root `.python-version` selects Python 3.13, `requirements.txt` requires binary wheels, and the Procfile starts Uvicorn on the Cloud Run port.

Export your existing `BFL_API_KEY`, `SECRET_KEY` and `ADMIN_PASSWORD` in your shell. Keep the same signing secret across deployments. To generate one on first setup, run `export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"`.

```sh
./scripts/deploy.sh
```

The script uses `gcloud run deploy --set-env-vars`. It replaces the service’s runtime environment variable list with the three required values and any optional app settings exported from the table below. Cloud Run stores these as ordinary revision configuration visible to users with permission to inspect the service. Set `BFL_MODEL=flux-3-image` in the environment to try FLUX 3; the application defaults to FLUX.2 Pro.

Keep exporting the original names on your machine. The script sends the three credentials as literal variables named `SALON_BFL_API_KEY`, `SALON_SECRET_KEY`, and `SALON_ADMIN_PASSWORD` on Cloud Run. In the same deployment it removes any Secret Manager bindings under the original three names. This works for both a first deployment and migration of an existing service. The secret entries in Secret Manager are untouched.

### Switch models on the deployed service

For the demo in Belgium, update the model with:

```sh
gcloud run services update hairstyle-simulator --region europe-west1 \
  --update-env-vars=BFL_MODEL=flux-3-image
```

Cloud Run starts a new revision using the existing image. This changes only the model setting and requires no source build or manual restart. Use the region where your service actually runs (for an existing Frankfurt deployment, use `europe-west3`). Deploying the source in Belgium creates a separate regional service. To switch back, repeat with `flux-2-pro`. Export the desired `BFL_MODEL` before the next source deployment if you want to keep it.

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
| PORT | Cloud Run supplies the listening port; Procfile fallback 8080 |

For manual bootstrap use `python scripts/create_admin.py --username admin --password …`. Existing SQLite catalogue IDs and legacy bcrypt passwords remain usable.

## Salon workflows

**Try a style.** Select a built-in or uploaded reference. Admins can preview a face cover before uploading. The gallery displays the original, while rendering uses the prepared copy. Covering the reference face is experimental. Compare repeated renders with the same selfie, cut and colour to evaluate identity and haircut accuracy separately.

**Suggest a cut.** A local frontal-face and eye detector supplies a rough framing cue when one frontal face and two consistent eye detections are available. Customer preferences determine the briefs. Missing landmarks fall back to preference-only ideas. The operator chooses and can edit a brief before the first billed generation. A front selfie cannot establish density, growth patterns or real-world suitability.

**Colour.** Keep the selfie colour, select a shade or enter a custom shade. Matching the reference colour is available in catalogue mode. Pin up to two results beside the original for discussion.

The four generated mannequin photographs under assets/hairstyles ship with every instance. No runtime image download or database seeding is required. The app uses wheel-bundled OpenCV cascades and has no MediaPipe model download or compiler requirement.

[BFL image editor API](https://docs.bfl.ml/api-reference/utility/generate-an-image-with-flux-3)

Run the integration checks with `python -m unittest discover -s tests`. They mock BFL and incur no generation charges.
