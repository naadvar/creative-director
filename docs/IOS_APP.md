# Shipping Creative Director to the App Store

How the iOS app is built and submitted. You're on Windows, so the build runs on a
**cloud Mac (Codemagic)** — you never need a Mac of your own.

## Architecture (already built)
- **Capacitor** wraps the existing React app — same codebase, no rewrite.
- The app **bundles** the web build (`frontend/dist`) rather than loading the live
  site, so Apple doesn't reject it as "just a website" (App Store rule 4.2).
- `npm run build:app` compiles the bundle with the API pointed at Railway
  (`frontend/.env.app`), since there's no Vercel `/api` proxy inside the app.
- **Auth uses a bearer token** (`/auth/email` returns one) because a native webview
  can't carry the session cookie. The web app is unchanged (cookie-only).
- **Video upload** uses the standard file input, which in the iOS webview opens the
  native Photos picker. (The `NSPhotoLibraryUsageDescription` permission is injected
  by `codemagic.yaml`.)

## One-time setup
1. **Apple Developer Program** — enroll at developer.apple.com ($99/yr).
2. **App Store Connect** → **My Apps** → **+** → create the app:
   - Name: **Creative Director** (if taken, try "Creative Director — Reel Reads").
   - Bundle ID: **com.creativedirector.app** — or register one you own under
     Certificates, IDs & Profiles, and update it in `capacitor.config.ts`,
     `codemagic.yaml`, and App Store Connect so all three match.
3. **App Store Connect API key** — Users and Access → Integrations → App Store
   Connect API → generate a key (Admin or App Manager role). Download the `.p8`.
4. **Codemagic** (codemagic.io, free tier) → connect this GitHub repo →
   Settings → code signing → add the App Store Connect API key, name the
   integration **`codemagic`** (matches `codemagic.yaml`). Codemagic auto-manages
   signing certs + provisioning from that key.
5. Push to `main` → run the **"Creative Director iOS"** workflow → it builds, signs,
   and uploads to **TestFlight**. Install via the TestFlight app on your iPhone to
   test. When happy, set `submit_to_app_store: true` (or submit from App Store
   Connect) for review.

## App icon + splash
Generate all sizes from one source with `@capacitor/assets`:
```
cd frontend
npm i -D @capacitor/assets
# put a 1024x1024 PNG at resources/icon.png and a 2732x2732 PNG at resources/splash.png
npx @capacitor/assets generate --ios
```
A brand-matched source (violet→cyan gradient, white play triangle) can be generated
from `scripts/tmp/gen_pwa_icons.py` (bump the size to 1024). Run this BEFORE the
Codemagic build, or add it as a build step.

## App Store listing copy (paste into App Store Connect)
- **Name:** Creative Director
- **Subtitle (30 chars):** A craft read of your reel
- **Promotional text:** Drop a reel, get the one craft fix you're too close to see.
- **Keywords:** reels,shorts,video editing,creator,content,craft,feedback,hook,pacing,tiktok
- **Description:**
  > Creative Director watches your short-form video frame by frame and hands you the
  > single highest-leverage craft fix — the thing you're too close to see. It reads
  > your hook, pacing, framing, payoff, and every on-screen text beat, grounded in
  > your actual footage.
  >
  > • Drop a reel (even an unposted draft) and get a craft read in ~2 minutes.
  > • One prioritized fix, tied to a moment in your video — tap to jump to it.
  > • See what's already working, plus blind spots worth a second look.
  > • Your reads build a Creator DNA that shows how your craft is trending.
  >
  > No virality promises. Nothing observable reliably predicts views — this reads the
  > craft of the video in front of it, like an editor catching things on a second watch.
- **Support URL:** https://creative-director-psi.vercel.app
- **Privacy Policy URL:** https://creative-director-psi.vercel.app/privacy

## App Privacy ("nutrition label" in App Store Connect)
- **Email address** — collected, linked to the user, used for App Functionality
  (sign-in) and Product Personalization (saving reads). Not used for tracking.
- **User Content (video/photos)** — collected, linked to the user, used for App
  Functionality (the analysis). Not used for tracking, not for third-party ads.
- **Tracking:** No. No data is used to track across apps/sites.

## Screenshots (required: 6.7" and 6.5" iPhone)
Capture 3–5 on an iPhone simulator or device:
1. The upload screen (the gradient hero + dropzone).
2. A craft read — the verdict + "Fix this first" lever.
3. My Reads (the gallery).
4. Creator DNA — the trend ("pacing was a recurring note… your last 2 cleared it").

## App Review notes (IMPORTANT — paste into "Notes" at submission)
> Sign-in is passwordless: on the "Sign in" screen, enter ANY email address (e.g.
> review@apple.com) and tap Sign in — no password, no confirmation needed. Then tap
> "Read my reel" and pick any short video from the photo library to see a craft read
> (analysis takes ~2 minutes).

This is the #1 reason passwordless apps get rejected — reviewers can't find how to
sign in. The note above prevents it.

## Android (optional, far easier — $25 one-time)
The same Capacitor project does Android: `npx cap add android` + a Codemagic Android
workflow → Play Store. Review is lenient. Worth doing once iOS is in TestFlight.
