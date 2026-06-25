# Native (Capacitor) build only — loaded by `vite build --mode app`.
# There is no Vercel /api proxy inside the app, so the bundled web assets must call
# the Railway API at its absolute URL. (The web build keeps using the relative /api.)
VITE_API_BASE=https://creative-director-api-production.up.railway.app
