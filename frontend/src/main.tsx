import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import '@fontsource-variable/inter/index.css'
import './index.css'
import App from './App.tsx'

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
