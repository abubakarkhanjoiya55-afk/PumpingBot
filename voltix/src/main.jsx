import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import { refreshReferralOrigin } from './lib/referral.js'
import './index.css'

refreshReferralOrigin().finally(() => {
  createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  )
})
