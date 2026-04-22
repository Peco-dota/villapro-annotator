import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { isLoggedIn } from './lib/auth'
import { LoginPage } from './pages/LoginPage'
import { WelcomePage } from './pages/WelcomePage'
import { AnnotatePage } from './pages/AnnotatePage'
import { DetectionPage } from './pages/DetectionPage'
import { SettingsPage } from './pages/SettingsPage'

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 5000 } },
})

function RequireAuth({ children }: { children: React.ReactNode }) {
  return isLoggedIn() ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<RequireAuth><WelcomePage /></RequireAuth>} />
          <Route path="/annotate" element={<RequireAuth><AnnotatePage /></RequireAuth>} />
          <Route path="/detection" element={<RequireAuth><DetectionPage /></RequireAuth>} />
          <Route path="/settings" element={<RequireAuth><SettingsPage /></RequireAuth>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
