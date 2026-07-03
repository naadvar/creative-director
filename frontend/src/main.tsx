import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import '@fontsource-variable/inter/index.css'
import './index.css'
import App from './App.tsx'
import { isNativeApp } from './api/client'

// Native app: pin the webview's text zoom to 100%. iOS applies the user's system
// text-size/page-zoom setting inside Capacitor webviews, which SCALES our CSS —
// at 115-150% the layout overflows sideways ("Sign in/out cut off" on load, seen
// in tester round 1) instead of adapting. Pinning keeps layout deterministic;
// users can still enlarge via OS-level zoom gestures.
if (isNativeApp()) {
  import('@capacitor/text-zoom')
    .then(({ TextZoom }) => TextZoom.set({ value: 1 }))
    .catch(() => {})
}

// Keep an open tab / installed PWA current. The service worker (registerType
// 'autoUpdate') already activates a new version and reloads automatically — but
// it only CHECKS for one on page load, so a tab left open never notices a deploy.
// Nudge it to re-check periodically and whenever the tab regains focus, so users
// (and the owner testing) always land on the latest without clearing cache.
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.ready
    .then((reg) => {
      const check = () => {
        reg.update().catch(() => {})
      }
      setInterval(check, 30 * 60 * 1000) // every 30 minutes
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') check()
      })
      // Native app: iOS doesn't reliably fire visibilitychange on app resume, so a
      // backgrounded app could serve a stale bundle. Also check on Capacitor's
      // 'resume' event so reopening the app pulls the latest deploy.
      if (isNativeApp()) {
        import('@capacitor/app')
          .then(({ App: CapApp }) => CapApp.addListener('resume', check))
          .catch(() => {})
      }
    })
    .catch(() => {})
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
