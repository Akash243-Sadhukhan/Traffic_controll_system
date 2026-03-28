import './DensityPanel.css';

const CONGESTION_STYLES = {
  LOW:      { color: '#22c55e', bg: 'rgba(34,197,94,0.1)',  border: 'rgba(34,197,94,0.25)',  icon: '🟢' },
  MEDIUM:   { color: '#f59e0b', bg: 'rgba(245,158,11,0.1)', border: 'rgba(245,158,11,0.25)', icon: '🟡' },
  HIGH:     { color: '#f43f5e', bg: 'rgba(244,63,94,0.1)',   border: 'rgba(244,63,94,0.25)',  icon: '🔴' },
  CRITICAL: { color: '#dc2626', bg: 'rgba(220,38,38,0.15)',  border: 'rgba(220,38,38,0.3)',   icon: '🚨' },
};

export default function DensityPanel({ density }) {
  const lanes = density?.lanes ?? {};
  const overall = density?.overall_congestion ?? 'LOW';
  const mostCongested = density?.most_congested ?? '';

  return (
    <div className="density-panel" id="density-panel">
      <div className="density-panel__header">
        <h3>Density Analysis</h3>
        <div className="density-panel__overall" style={{
          color: CONGESTION_STYLES[overall]?.color,
          background: CONGESTION_STYLES[overall]?.bg,
          borderColor: CONGESTION_STYLES[overall]?.border,
        }}>
          {CONGESTION_STYLES[overall]?.icon} {overall}
        </div>
      </div>

      <div className="density-panel__lanes">
        {Object.entries(lanes).map(([lane, info]) => {
          const level = info.congestion ?? 'LOW';
          const style = CONGESTION_STYLES[level] ?? CONGESTION_STYLES.LOW;
          const pct = Math.min((info.vehicle_count ?? 0) / 15 * 100, 100);

          return (
            <div key={lane} className={`density-lane ${mostCongested === lane ? 'most-congested' : ''}`}>
              <div className="density-lane__top">
                <span className="density-lane__name">{lane.toUpperCase()}</span>
                <span className="density-lane__count" style={{ color: style.color }}>
                  {info.vehicle_count ?? 0}
                </span>
              </div>
              <div className="density-lane__bar-track">
                <div
                  className="density-lane__bar-fill"
                  style={{
                    width: `${pct}%`,
                    background: `linear-gradient(90deg, ${style.color}88, ${style.color})`,
                    boxShadow: `0 0 8px ${style.color}44`,
                  }}
                />
              </div>
              <div className="density-lane__bottom">
                <span className="density-lane__level" style={{ color: style.color }}>
                  {level}
                </span>
                <span className="density-lane__trend">
                  {info.trend === 'increasing' ? '📈' : info.trend === 'decreasing' ? '📉' : '➡️'}
                  {' '}{info.trend ?? 'stable'}
                </span>
                <span className="density-lane__ext">
                  +{info.recommended_green_extension ?? 0}s
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
