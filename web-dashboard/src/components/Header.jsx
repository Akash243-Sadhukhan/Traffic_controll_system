import { useState, useEffect } from 'react';
import './Header.css';

export default function Header({ isConnected, stats }) {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="header" id="main-header">
      <div className="header__left">
        <div className="header__logo">
          <span className="header__logo-icon">🚦</span>
          <div>
            <h1 className="header__title">Traffic AI</h1>
            <p className="header__subtitle">Adaptive Signal Control</p>
          </div>
        </div>
      </div>

      <div className="header__center">
        <div className="header__stat">
          <span className="header__stat-label">Vehicles</span>
          <span className="header__stat-value">{stats?.total_vehicles ?? '—'}</span>
        </div>
        <div className="header__divider" />
        <div className="header__stat">
          <span className="header__stat-label">FPS</span>
          <span className="header__stat-value">{stats?.fps ?? '—'}</span>
        </div>
        <div className="header__divider" />
        <div className="header__stat">
          <span className="header__stat-label">Frames</span>
          <span className="header__stat-value">
            {stats?.frame_count?.toLocaleString() ?? '—'}
          </span>
        </div>
      </div>

      <div className="header__right">
        <div className={`header__connection ${isConnected ? 'connected' : 'disconnected'}`}>
          <span className="header__connection-dot" />
          <span>{isConnected ? 'Live' : 'Offline'}</span>
        </div>
        <div className="header__time">{time.toLocaleTimeString()}</div>
      </div>
    </header>
  );
}
