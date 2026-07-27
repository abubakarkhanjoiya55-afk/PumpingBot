import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export default function AppShell() {
  const { user } = useAuth()
  return (
    <div className="appShell">
      <header className="topbar">
        <div className="topbarInner">
          <NavLink to="/app" className="logo" end>
            Voltix
          </NavLink>
          <div className="topActions">
            <Link className="userChip" to="/app/settings">
              {user?.name || 'User'}
            </Link>
          </div>
        </div>
      </header>
      <div className="wrap">
        <Outlet />
      </div>
      <nav className="tabbar tabbar5" aria-label="App">
        <NavLink to="/app" end>
          <span>⌂</span>Home
        </NavLink>
        <NavLink to="/app/plans">
          <span>◆</span>Stake
        </NavLink>
        <NavLink to="/app/team">
          <span>▣</span>Team
        </NavLink>
        <NavLink to="/app/deposit">
          <span>↓</span>Deposit
        </NavLink>
        <NavLink to="/app/withdraw">
          <span>↑</span>Withdraw
        </NavLink>
      </nav>
    </div>
  )
}
