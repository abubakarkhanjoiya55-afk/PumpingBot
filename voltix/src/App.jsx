import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext.jsx'
import PublicShell from './components/PublicShell.jsx'
import AppShell from './components/AppShell.jsx'
import RequireAuth from './components/RequireAuth.jsx'
import Home from './pages/Home.jsx'
import About from './pages/About.jsx'
import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Plans from './pages/Plans.jsx'
import Team from './pages/Team.jsx'
import Deposit from './pages/Deposit.jsx'
import Withdraw from './pages/Withdraw.jsx'
import Settings from './pages/Settings.jsx'
import SettingsAbout from './pages/SettingsAbout.jsx'
import AdminLogin from './pages/AdminLogin.jsx'
import Admin from './pages/Admin.jsx'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<PublicShell />}>
            <Route path="/" element={<Home />} />
            <Route path="/about" element={<About publicMode />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
          </Route>
          <Route path="/admin/login" element={<AdminLogin />} />
          <Route path="/admin" element={<Admin />} />
          <Route
            path="/app"
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="plans" element={<Plans />} />
            <Route path="team" element={<Team />} />
            <Route path="deposit" element={<Deposit />} />
            <Route path="withdraw" element={<Withdraw />} />
            <Route path="settings" element={<Settings />} />
            <Route path="settings/about" element={<SettingsAbout />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
