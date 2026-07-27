export default function Toast({ type, children }) {
  if (!children) return null
  return <div className={`toast ${type || ''}`.trim()}>{children}</div>
}
