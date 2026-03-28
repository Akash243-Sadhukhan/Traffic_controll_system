import './TrafficMap.css';

const SIGNAL_COLORS = {
  RED: '#ef4444',
  YELLOW: '#eab308',
  GREEN: '#22c55e',
};

export default function TrafficMap({ signals, stats }) {
  const states = signals?.states ?? { north: 'RED', south: 'RED', east: 'RED', west: 'RED' };
  const activeLane = signals?.active_lane ?? '';
  const armCounts = stats?.arm_counts ?? {};

  return (
    <div className="traffic-map" id="traffic-map-panel">
      <div className="traffic-map__header">
        <h3>Intersection View</h3>
        <span className="traffic-map__mode">{signals?.mode ?? 'ADAPTIVE'}</span>
      </div>

      <div className="traffic-map__visual">
        <svg viewBox="0 0 400 400" className="traffic-map__svg">
          {/* Road grid */}
          <rect x="150" y="0" width="100" height="400" fill="#1e293b" rx="2" />
          <rect x="0" y="150" width="400" height="100" fill="#1e293b" rx="2" />

          {/* Center intersection */}
          <rect x="150" y="150" width="100" height="100" fill="#0f172a" />

          {/* Lane markings */}
          <line x1="200" y1="0" x2="200" y2="145" stroke="#475569" strokeWidth="1.5" strokeDasharray="12 8" />
          <line x1="200" y1="255" x2="200" y2="400" stroke="#475569" strokeWidth="1.5" strokeDasharray="12 8" />
          <line x1="0" y1="200" x2="145" y2="200" stroke="#475569" strokeWidth="1.5" strokeDasharray="12 8" />
          <line x1="255" y1="200" x2="400" y2="200" stroke="#475569" strokeWidth="1.5" strokeDasharray="12 8" />

          {/* Crosswalk stripes */}
          {[0,1,2,3,4].map(i => (
            <g key={`crosswalk-${i}`}>
              <rect x={155 + i*18} y="145" width="10" height="5" fill="#475569" opacity="0.4" />
              <rect x={155 + i*18} y="250" width="10" height="5" fill="#475569" opacity="0.4" />
              <rect x="145" y={155 + i*18} width="5" height="10" fill="#475569" opacity="0.4" />
              <rect x="250" y={155 + i*18} width="5" height="10" fill="#475569" opacity="0.4" />
            </g>
          ))}

          {/* Traffic signals — North */}
          <g className={`signal-group ${activeLane === 'north' ? 'active' : ''}`}>
            <circle cx="200" cy="60" r="18" fill={SIGNAL_COLORS[states.north]}
              opacity={states.north === 'GREEN' ? 1 : 0.4}
              className={states.north === 'GREEN' ? 'signal-glow' : ''} />
            <circle cx="200" cy="60" r="18" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" />
            <text x="200" y="100" textAnchor="middle" fill="#94a3b8" fontSize="11" fontWeight="600">N</text>
            <text x="200" y="115" textAnchor="middle" fill={SIGNAL_COLORS[states.north]}
              fontSize="13" fontWeight="700" fontFamily="'JetBrains Mono'">{armCounts.north ?? 0}</text>
          </g>

          {/* South */}
          <g className={`signal-group ${activeLane === 'south' ? 'active' : ''}`}>
            <circle cx="200" cy="340" r="18" fill={SIGNAL_COLORS[states.south]}
              opacity={states.south === 'GREEN' ? 1 : 0.4}
              className={states.south === 'GREEN' ? 'signal-glow' : ''} />
            <circle cx="200" cy="340" r="18" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" />
            <text x="200" y="310" textAnchor="middle" fill="#94a3b8" fontSize="11" fontWeight="600">S</text>
            <text x="200" y="295" textAnchor="middle" fill={SIGNAL_COLORS[states.south]}
              fontSize="13" fontWeight="700" fontFamily="'JetBrains Mono'">{armCounts.south ?? 0}</text>
          </g>

          {/* East */}
          <g className={`signal-group ${activeLane === 'east' ? 'active' : ''}`}>
            <circle cx="340" cy="200" r="18" fill={SIGNAL_COLORS[states.east]}
              opacity={states.east === 'GREEN' ? 1 : 0.4}
              className={states.east === 'GREEN' ? 'signal-glow' : ''} />
            <circle cx="340" cy="200" r="18" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" />
            <text x="305" y="204" textAnchor="middle" fill="#94a3b8" fontSize="11" fontWeight="600">E</text>
            <text x="290" y="204" textAnchor="middle" fill={SIGNAL_COLORS[states.east]}
              fontSize="13" fontWeight="700" fontFamily="'JetBrains Mono'">{armCounts.east ?? 0}</text>
          </g>

          {/* West */}
          <g className={`signal-group ${activeLane === 'west' ? 'active' : ''}`}>
            <circle cx="60" cy="200" r="18" fill={SIGNAL_COLORS[states.west]}
              opacity={states.west === 'GREEN' ? 1 : 0.4}
              className={states.west === 'GREEN' ? 'signal-glow' : ''} />
            <circle cx="60" cy="200" r="18" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5" />
            <text x="95" y="204" textAnchor="middle" fill="#94a3b8" fontSize="11" fontWeight="600">W</text>
            <text x="110" y="204" textAnchor="middle" fill={SIGNAL_COLORS[states.west]}
              fontSize="13" fontWeight="700" fontFamily="'JetBrains Mono'">{armCounts.west ?? 0}</text>
          </g>

          {/* Center label */}
          <text x="200" y="196" textAnchor="middle" fill="#64748b" fontSize="9" fontWeight="600"
            letterSpacing="0.08em">JUNCTION</text>
          <text x="200" y="212" textAnchor="middle" fill="#38bdf8" fontSize="11" fontWeight="700"
            fontFamily="'JetBrains Mono'">
            {Object.values(armCounts).reduce((a, b) => a + b, 0)}
          </text>
        </svg>
      </div>

      <div className="traffic-map__footer">
        <span className="traffic-map__elapsed">
          Phase: {signals?.phase_elapsed?.toFixed(0) ?? 0}s
        </span>
        {signals?.pending_lane && (
          <span className="traffic-map__pending">
            Next → {signals.pending_lane.toUpperCase()}
          </span>
        )}
      </div>
    </div>
  );
}
