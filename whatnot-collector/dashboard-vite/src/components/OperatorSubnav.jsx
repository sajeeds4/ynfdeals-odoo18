import { Link, useLocation } from 'react-router-dom';

const ITEMS = [
  { to: '/operator', label: 'Main Operator', exact: true },
  { to: '/operator/tv-scanner', label: 'TV Scanner' },
  { to: '/operator/winner-scanner', label: 'Winner Scanner' },
  { to: '/operator/obs', label: 'OBS Operator' },
];

export default function OperatorSubnav() {
  const loc = useLocation();

  return (
    <div className="operator-subnav">
      {ITEMS.map((item) => {
        const active = item.exact ? loc.pathname === item.to : loc.pathname.startsWith(item.to);
        return (
          <Link
            key={item.to}
            to={item.to}
            className={`operator-subnav__link ${active ? 'active' : ''}`}
          >
            {item.label}
          </Link>
        );
      })}
    </div>
  );
}
