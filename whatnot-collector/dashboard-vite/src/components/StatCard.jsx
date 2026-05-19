/**
 * StatCard — compact metric display.
 */
export default function StatCard({ label, value, sub, color, icon }) {
  return (
    <div className="stat-card">
      <div className="stat-card__label">
        {icon && <span className="stat-card__icon">{icon}</span>}
        {label}
      </div>
      <div className="stat-card__value" style={color ? { color } : undefined}>
        {value}
      </div>
      {sub && <div className="stat-card__sub">{sub}</div>}
    </div>
  );
}
