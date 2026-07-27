import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export default function RequireAuth({ children }) {
  const { isAuthed, ready } = useAuth()
  if (!ready) {
    return (
      <div className="bootScreen" aria-busy="true">
        Loading Voltix…
      </div>
    )
  }
  if (!isAuthed) return <Navigate to="/login" replace />
  return children
}
