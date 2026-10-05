import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './app/App'
import { ErrorBoundary } from './ErrorBoundary'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary
      fullPage
      onBack={() => {
        window.history.replaceState({}, '', window.location.pathname)
        window.location.reload()
      }}
      backLabel="返回制作页"
    >
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
