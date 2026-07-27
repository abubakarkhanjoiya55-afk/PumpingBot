export default function PasswordField({
  id,
  label = 'Password',
  value,
  onChange,
  autoComplete = 'current-password',
  required = true,
  minLength,
  show,
  onToggle,
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="passwordWrap">
        <input
          id={id}
          type={show ? 'text' : 'password'}
          autoComplete={autoComplete}
          value={value}
          onChange={onChange}
          required={required}
          minLength={minLength}
        />
        <button
          type="button"
          className="passwordToggle"
          onClick={onToggle}
          aria-label={show ? 'Hide password' : 'Show password'}
        >
          {show ? 'Hide' : 'Show'}
        </button>
      </div>
    </div>
  )
}
