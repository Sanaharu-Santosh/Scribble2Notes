# Getting Cloud Vision working

About fifteen minutes, most of it waiting on Google's console. You need a Google
account and a credit card on file for the free tier — you will not be charged at
development volumes.

**Cost:** the first 1,000 images per month are free. After that it's $1.50 per
1,000 (dropping to $0.60 per 1,000 above five million). One image = one unit; a
multi-page PDF counts each page separately.

The fixture workflow in step 6 exists so you spend those 1,000 units on real
checks rather than on re-running the same page while styling the overlay.

---

## 1. Create a project

In the [Cloud console](https://console.cloud.google.com/), create a project (or
pick one you already have). Note the **project ID** — not the display name; it's
the one with the random suffix, like `scribble2notes-481207`.

## 2. Enable the Vision API

Enable `vision.googleapis.com` for that project — search "Cloud Vision API" in
the console and click **Enable**, or:

```bash
gcloud services enable vision.googleapis.com --project PROJECT_ID
```

Nothing works until this is done, and the error you get otherwise (`403
PERMISSION_DENIED`) does not obviously say so.

## 3. Authenticate

Two ways. Use the first one locally.

### Option A — application default credentials (recommended for development)

No key file to leak, nothing that can be committed by accident.

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project PROJECT_ID
```

> **Leave `GOOGLE_APPLICATION_CREDENTIALS` unset** — commented out in
> `backend/.env`. Application default credentials are only consulted when that
> variable is *absent*, so a leftover path silently overrides your login.

### Option B — service account key (for deployment, Phase 7)

In **IAM & Admin → Service Accounts**, create an account, give it the
**Cloud Vision AI Service Agent** role, then create a JSON key and download it.
Store it outside the repo, and point `backend/.env` at it:

```dotenv
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
```

The app copies that value into the process environment at client construction —
the Google library only reads the environment variable and knows nothing about
our `.env` file.

`.gitignore` already excludes `*-service-account*.json` and `credentials.json`,
but the safest place for a key is still outside the repository.

## 4. Install the client library

```bash
cd backend
pip install -r requirements-cloud.txt
```

Kept out of `requirements.txt` on purpose, so the default install and the
production image stay small.

## 5. Point the app at it

In `backend/.env`:

```dotenv
OCR_ENGINE=cloud_vision
OCR_GRANULARITY=line
```

## 6. Verify — and capture a fixture

Run a page through it without starting the server:

```bash
python scripts/try_engine.py --image path/to/your/notes.jpg --engine cloud_vision --save-fixture
```

You should see one row per line, with confidence, position, slant and text. Good
signs:

- the line count matches the page
- confidences are mostly above 80%
- slants are non-zero if the writing is slanted

If lines look wrongly merged or split, re-run with `--granularity word`. That
separates the two possible faults: if the individual words are right, the line
grouping is at fault (`group_into_lines`); if the words themselves are wrong,
it's detection, and no amount of grouping will fix it.

`--save-fixture` writes `fixtures/lens_fixture.json`.

## 7. Work offline against real output

```dotenv
OCR_ENGINE=fixture
```

Now every upload replays that saved response — real Cloud Vision output, zero
quota, no network. The UI labels it `fixture<cloud_vision>` and still shows the
mock banner, so it can never be mistaken for a live call.

Switch back to `cloud_vision` when you want to test a different page.

---

## When it doesn't work

| What you see | What it usually means |
| --- | --- |
| `403 PERMISSION_DENIED` | The API isn't enabled on this project (step 2), or the key belongs to a different project |
| `DefaultCredentialsError` | Neither option A nor B completed — no ADC login, no key path |
| `Could not create a Cloud Vision client` | The path in `GOOGLE_APPLICATION_CREDENTIALS` doesn't exist or isn't valid JSON |
| `google-cloud-vision is not installed` | Step 4 |
| Works in the script, fails in the app | Different shell, different environment — the server process didn't inherit your `gcloud` login. Restart uvicorn from the same terminal |
| Empty `regions`, no error | Vision found no text. Usually a very low-contrast photo; try better lighting before suspecting the code |
| Quota errors after a while | You're past the free 1,000. Switch to `OCR_ENGINE=fixture` for day-to-day work |
