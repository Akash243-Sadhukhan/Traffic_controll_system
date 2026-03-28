import './StatsCards.css';

const CARDS = [
  {
    id: 'total-vehicles',
    label: 'Active Vehicles',
    icon: '🚗',
    key: 'total_vehicles',
    gradient: 'var(--gradient-primary)',
    fallback: 0,
  },
  {
    id: 'detection-fps',
    label: 'Detection FPS',
    icon: '⚡',
    key: 'fps',
    gradient: 'var(--gradient-emerald)',
    fallback: 0,
  },
  {
    id: 'ws-clients',
    label: 'WS Clients',
    icon: '🔌',
    key: 'websocket_clients',
    gradient: 'linear-gradient(135deg, #8b5cf6, #ec4899)',
    fallback: 0,
  },
  {
    id: 'detection-active',
    label: 'Detection',
    icon: '🎯',
    key: 'detection_running',
    gradient: 'var(--gradient-danger)',
    isBoolean: true,
    fallback: false,
  },
];

export default function StatsCards({ stats }) {
  return (
    <div className="stats-cards" id="stats-cards-panel">
      {CARDS.map((card, i) => {
        const raw = stats?.[card.key] ?? card.fallback;
        const display = card.isBoolean
          ? (raw ? 'Running' : 'Stopped')
          : (typeof raw === 'number' ? raw.toLocaleString() : raw);

        return (
          <div
            className="stats-card animate-slide-up"
            id={card.id}
            key={card.id}
            style={{ animationDelay: `${i * 80}ms`, '--card-gradient': card.gradient }}
          >
            <div className="stats-card__accent" />
            <div className="stats-card__icon">{card.icon}</div>
            <div className="stats-card__content">
              <span className="stats-card__value">{display}</span>
              <span className="stats-card__label">{card.label}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
