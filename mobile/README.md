# mobile — RoadWatch citizen app

React Native with **Expo SDK 57** and **Expo Router** (routes in `src/app/`). One codebase
for Android and iOS; also builds for web (used for automated testing).

| Tab / screen | What it does |
|---|---|
| Sign in (`login.tsx`) | Phone number → one-time code. The number goes only to the identity vault; the app gets a token carrying an anonymous id, kept in the phone's secure storage |
| **Report** (`(tabs)/index.tsx`) | Live camera only → GPS + time captured at the same moment → pick category → submit → watch verification ("What we checked") |
| **My reports** | Your submissions and their status (checking / verified / not verified, with reasons) |
| **Nearby** | Map + list of issues within 1.5 km, nearest first; **"I see this too"** when you're within 150 m (counted as a sighting, not a verified report) |
| **Inbox** | "Is it fixed?" questions with the authority's repair photo (Yes / Partly / No), and notifications |
| Issue page (`ticket/[ref].tsx`) | Public view of an issue: status, reporters, deadline, cleaned photos |

## No gallery uploads

The app has **no way to pick an existing photo**: no image picker, media library or file
input anywhere. `npm test` runs `scripts/check-no-gallery.mjs`, which fails if one is ever
added. The API also refuses uploads not marked `capture_source=in_app_camera`. Real
device attestation (Play Integrity / App Attest) is the next hardening step (Phase 5).

## Run it on your phone (Expo Go, free)

1. Install **Expo Go** from the Play Store / App Store.
2. Start the backend (see the main README). The API must be reachable from the phone,
   so use your computer's LAN address:

   ```bash
   cd mobile
   npm install
   EXPO_PUBLIC_API_URL=http://192.168.1.20:8000 npx expo start   # your computer's IP
   ```

3. Scan the QR code with Expo Go (Android) or the Camera app (iOS).
4. Sign in with any Indian mobile number; the one-time code is printed in the API log
   (`docker compose logs api | grep "OTP STUB"`), because SMS is stubbed.

Everything used (camera, location, secure storage, WebView) is included in Expo Go, so
no custom build is needed. For store builds use EAS (`npx eas-cli@latest build`).

The Nearby map loads MapLibre and OpenFreeMap tiles from the internet (free, no key);
without internet it shows a notice and the list still works.

## Checks

```bash
npm run typecheck        # TypeScript
npm test                 # unit tests (Node's test runner) + the no-gallery check
npx expo export --platform android   # bundles the whole app for Android (catches bad imports)
```

### End-to-end test (web build in Chromium, fake camera + GPS)

```bash
# API with inline verification, CORS for the web build, log captured for OTP codes:
TASKS_EAGER=true CORS_ORIGINS='["http://localhost:8081"]' uvicorn app.main:app --port 8000 > /tmp/api.log 2>&1 &
npx expo export --platform web --output-dir dist-web      # then serve dist-web on :8081 with SPA fallback
python -m app.seed.photos /tmp/fake-camera.mjpeg          # (in backend/) a fresh synthetic "pothole"
API_LOG=/tmp/api.log FAKE_CAMERA=/tmp/fake-camera.mjpeg npx playwright test
```

The test signs in with a code read from the log, takes a photo with the fake camera,
submits a pothole, checks it's verified and appears under Nearby, then has the KMC
official submit a repair photo and answers "Yes, fixed" from the Inbox.

## Not yet done

- **Push notifications** are a stub; the Inbox refreshes when opened. Real push needs a
  device push token stored against the reporter. That token is linked to a physical
  phone, so where to store it (identity vault vs. ticket database) is an anonymity
  decision to make first. See the Phase 4 notes in the main README.
- **Hindi / Bengali** strings: labels are plain English in the screens for now.
- **Device attestation**: stubbed (Phase 5).
