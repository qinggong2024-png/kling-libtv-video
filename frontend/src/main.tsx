import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './app/App'
import { createCreativeProject } from './creative-project/project'
import { CreativeProjectProvider } from './creative-project/provider'
import { ErrorBoundary } from './ErrorBoundary'
import './styles.css'

const initialCreativeProject = createCreativeProject({
  id: 'local-creative-project',
  name: 'Creative Project',
})

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
      <CreativeProjectProvider initialProject={initialCreativeProject}>
        <App />
      </CreativeProjectProvider>
    </ErrorBoundary>
  </StrictMode>,
)
