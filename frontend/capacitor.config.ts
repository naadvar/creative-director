import type { CapacitorConfig } from '@capacitor/cli'

// The native app BUNDLES the built web assets (webDir: 'dist') rather than loading
// the live site in a webview — Apple rejects "just a website" wrappers (rule 4.2),
// and bundling is faster + works offline. Because there's no Vercel /api proxy inside
// the app, the native build is compiled with VITE_API_BASE pointing straight at the
// Railway API (see `npm run build:app`), and auth uses a bearer token (cookies don't
// flow cross-origin from capacitor://localhost) — see the native auth path.
const config: CapacitorConfig = {
  appId: 'com.creativedirector.app', // change to a bundle id you own before submitting
  appName: 'Creative Director',
  webDir: 'dist',
  ios: {
    contentInset: 'always',
  },
}

export default config
