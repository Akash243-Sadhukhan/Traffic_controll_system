import './SignalStatus.css';

const LANES = ['north', 'south', 'east', 'west'];

const LIGHT_STYLES = {
  RED: { color: '#ef4444', shadow: '0 0 12px rgba(239,68,68,0.5)', label: 'STOP' },
  YELLOW: { color: '#eab308', shadow: '0 0 12px rgba(234,179,8,0.5)', label: 'CAUTION' },
  GREEN: { color: '#22c55e', shadow: '0 0 12px rgba(34,197,94,0.5)', label: 'GO' },
};

export default function SignalStatus({ signals, mode = 'ADAPTIVE' }) {
  const states = signals?.states ?? {};
  const activeLane = signals?.active_lane ?? '';
  const elapsed = signals?.phase_elapsed ?? 0;

  return (
    <div className="signal-status" id="signal-status-panel">
      <div className="signal-status__header">
        <div className="signal-status__title-group">
          <h3>Traffic Signals</h3>
          <span className={`signal-status__mode-badge ${mode === 'RL' ? 'rl' : 'adaptive'}`}>
            {mode === 'RL' ? '🧠 RL MODEL' : '⚙️ ADAPTIVE'}
          </span>
        </div>
        <span className="signal-status__timer">{elapsed.toFixed(0)}s</span>
      </div>

      <div className="signal-status__grid">
        {LANES.map(lane => {
          const state = states[lane] ?? 'RED';
          const style = LIGHT_STYLES[state];
          const isActive = lane === activeLane;

          return (
            <div key={lane} className={`signal-light ${isActive ? 'active' : ''}`}>
              <div className="signal-light__housing">
                {['RED', 'YELLOW', 'GREEN'].map(s => (
                  <div
                    key={s}
                    className={`signal-light__bulb ${state === s ? 'lit' : ''}`}
                    style={{
                      '--bulb-color': LIGHT_STYLES[s].color,
                      boxShadow: state === s ? LIGHT_STYLES[s].shadow : 'none',
                    }}
                  />
                ))}
              </div>
              <div className="signal-light__info">
                <span className="signal-light__lane">{lane.toUpperCase()}</span>
                <span className="signal-light__state" style={{ color: style.color }}>
                  {style.label}
                </span>
              </div>
              {isActive && <div className="signal-light__active-badge">ACTIVE</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
