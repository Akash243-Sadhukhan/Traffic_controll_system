/**
 * useWebSocket.js — React hook for WebSocket connection with auto-reconnect.
 */
import { useState, useEffect, useRef, useCallback } from 'react';

const DEFAULT_URL = 'ws://localhost:8001/ws';
const RECONNECT_DELAY = 3000;
const MAX_RECONNECTS = 10;

export function useWebSocket(url = DEFAULT_URL) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState(null);
  const [stats, setStats] = useState(null);
  const [signals, setSignals] = useState(null);
  const [density, setDensity] = useState(null);
  const [detections, setDetections] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const wsRef = useRef(null);
  const reconnectCount = useRef(0);
  const reconnectTimer = useRef(null);

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        reconnectCount.current = 0;
        console.log('🔌 WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          setLastMessage(message);

          switch (message.type) {
            case 'stats':
              setStats(message.data);
              break;
            case 'signals':
              setSignals(message.data);
              break;
            case 'density':
              setDensity(message.data);
              break;
            case 'detections':
              setDetections(prev => [message.data, ...prev].slice(0, 50));
              break;
            case 'alerts':
              setAlerts(prev => [message.data, ...prev].slice(0, 20));
              break;
            default:
              break;
          }
        } catch (err) {
          console.warn('Failed to parse WebSocket message:', err);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        wsRef.current = null;

        if (reconnectCount.current < MAX_RECONNECTS) {
          reconnectCount.current += 1;
          console.log(`🔄 Reconnecting (${reconnectCount.current}/${MAX_RECONNECTS})...`);
          reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY);
        }
      };

      ws.onerror = (err) => {
        console.warn('WebSocket error:', err);
      };
    } catch (err) {
      console.error('WebSocket connection failed:', err);
    }
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  const send = useCallback((data) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  return {
    isConnected,
    lastMessage,
    stats,
    signals,
    density,
    detections,
    alerts,
    send,
  };
}
