import { useState, useEffect, useCallback } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { api } from './services/api';
import Header from './components/Header';
import StatsCards from './components/StatsCards';
import TrafficMap from './components/TrafficMap';
import LiveChart from './components/LiveChart';
import SignalStatus from './components/SignalStatus';
import DensityPanel from './components/DensityPanel';
import EventLog from './components/EventLog';
import LiveVideoFeed from './components/LiveVideoFeed';
import './App.css';

const POLL_INTERVAL = 2000; // 2s fallback polling

export default function App() {
  const { isConnected, stats: wsStats, signals: wsSignals, density: wsDensity, detections } = useWebSocket();

  // Fallback polling state (used when WebSocket is disconnected)
  const [polledStats, setPolledStats] = useState(null);
  const [polledSignals, setPolledSignals] = useState(null);
  const [polledDensity, setPolledDensity] = useState(null);

  // Use WebSocket data if available, else fallback to polling
  const stats = wsStats ?? polledStats;
  const signals = wsSignals ?? polledSignals?.signal_state ?? polledSignals;
  const density = wsDensity ?? polledDensity;

  // View state mapping
  const [activeTab, setActiveTab] = useState('trafficMap');

  // Fallback REST polling
  const poll = useCallback(async () => {
    if (isConnected) return; // WebSocket is handling it
    try {
      const [s, d] = await Promise.all([api.getStats(), api.getDensity()]);
      if (s) {
        setPolledStats(s);
        setPolledSignals(s.signal_state ?? s);
      }
      if (d) setPolledDensity(d);
    } catch {
      // ignore
    }
  }, [isConnected]);

  useEffect(() => {
    poll(); // initial fetch
    const timer = setInterval(poll, POLL_INTERVAL);
    return () => clearInterval(timer);
  }, [poll]);

  return (
    <div className="app">
      <Header isConnected={isConnected} stats={stats} />

      <main className="dashboard">
        {/* Stats cards */}
        <StatsCards stats={stats} />

        {/* Main panels */}
        <div className="dashboard__main">
          <div className="dashboard__col">
            <div className="view-toggle-container">
              <div className="view-toggle">
                <button
                  className={activeTab === 'trafficMap' ? 'active' : ''}
                  onClick={() => setActiveTab('trafficMap')}
                >
                  Intersection Map
                </button>
                <button
                  className={activeTab === 'liveFeed' ? 'active' : ''}
                  onClick={() => setActiveTab('liveFeed')}
                >
                  Live AI Feed
                </button>
              </div>
            </div>
            
            {activeTab === 'trafficMap' ? (
              <TrafficMap signals={signals} stats={stats} />
            ) : (
              <LiveVideoFeed />
            )}
            
            <SignalStatus signals={signals} mode={signals?.mode || 'ADAPTIVE'} />
          </div>
          <div className="dashboard__col">
            <LiveChart stats={stats} />
            <DensityPanel density={density} />
          </div>
        </div>

        {/* Bottom */}
        <div className="dashboard__bottom">
          <EventLog detections={detections} />
          <div className="polling-bar">
            <span className="polling-bar__dot" />
            {isConnected
              ? 'Live data via WebSocket'
              : `Polling every ${POLL_INTERVAL / 1000}s (WebSocket offline)`
            }
          </div>
        </div>
      </main>
    </div>
  );
}
