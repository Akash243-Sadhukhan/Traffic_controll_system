import { useState, useEffect } from 'react';
import { api } from '../services/api';
import './EventLog.css';

export default function EventLog({ detections = [] }) {
  const [history, setHistory] = useState([]);

  // Fetch initial history on mount
  useEffect(() => {
    api.getHistory('phase_change', null, 20).then(data => {
      if (Array.isArray(data)) setHistory(data);
    });
  }, []);

  // Merge live detections with history
  const events = detections.length > 0 ? detections : history;

  return (
    <div className="event-log" id="event-log-panel">
      <div className="event-log__header">
        <h3>Event Log</h3>
        <span className="event-log__count">{events.length} events</span>
      </div>

      <div className="event-log__body">
        {events.length === 0 ? (
          <div className="event-log__empty">
            <span className="event-log__empty-icon">📡</span>
            <p>Waiting for events…</p>
          </div>
        ) : (
          <div className="event-log__list">
            {events.slice(0, 15).map((ev, i) => {
              const isAlert = ev.severity === 'critical' || ev.is_emergency;
              const type = ev.event_type ?? ev.vehicle_class ?? 'event';

              return (
                <div
                  key={i}
                  className={`event-log__item ${isAlert ? 'alert' : ''} animate-fade-in`}
                  style={{ animationDelay: `${i * 40}ms` }}
                >
                  <div className="event-log__dot" style={{
                    background: isAlert ? 'var(--accent-rose)' : 'var(--accent-cyan)',
                  }} />
                  <div className="event-log__content">
                    <span className="event-log__type">{type}</span>
                    <span className="event-log__detail">
                      {ev.data?.reason ?? ev.data?.message ?? ev.lane ?? ''}
                    </span>
                  </div>
                  <span className="event-log__time">
                    {ev.timestamp
                      ? new Date(ev.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                      : '—'
                    }
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
