import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { loadConfig } from './config.js'

// Resolve runtime config (demo vs production) before first render so demo UI and
// auto-login decisions are made with the correct, server-provided values.
loadConfig().finally(() => {
  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
