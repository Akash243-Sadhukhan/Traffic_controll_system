import { useState, useEffect, useRef } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import './LiveChart.css';

const MAX_POINTS = 40;

const LANE_COLORS = {
  north: '#3b82f6',
  south: '#10b981',
  east: '#f59e0b',
  west: '#8b5cf6',
};

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload) return null;
  return (
    <div className="chart-tooltip">
      <p className="chart-tooltip__time">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="chart-tooltip__item" style={{ color: p.color }}>
          {p.name.toUpperCase()}: <strong>{p.value}</strong>
        </p>
      ))}
    </div>
  );
};

export default function LiveChart({ stats }) {
  const [data, setData] = useState([]);
  const countRef = useRef(0);

  useEffect(() => {
    if (!stats?.arm_counts) return;
    countRef.current += 1;

    setData(prev => {
      const next = [
        ...prev,
        {
          time: countRef.current,
          label: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          north: stats.arm_counts.north ?? 0,
          south: stats.arm_counts.south ?? 0,
          east: stats.arm_counts.east ?? 0,
          west: stats.arm_counts.west ?? 0,
        },
      ];
      return next.length > MAX_POINTS ? next.slice(-MAX_POINTS) : next;
    });
  }, [stats]);

  return (
    <div className="live-chart" id="live-chart-panel">
      <div className="live-chart__header">
        <h3>Vehicle Count — Real-time</h3>
        <span className="live-chart__points">{data.length} points</span>
      </div>

      <div className="live-chart__body">
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={data} margin={{ top: 5, right: 15, left: -15, bottom: 0 }}>
            <defs>
              {Object.entries(LANE_COLORS).map(([lane, color]) => (
                <linearGradient key={lane} id={`grad-${lane}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={color} stopOpacity={0.02} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 6" stroke="rgba(148,163,184,0.08)" />
            <XAxis
              dataKey="label"
              tick={{ fill: '#64748b', fontSize: 10 }}
              axisLine={{ stroke: 'rgba(148,163,184,0.1)' }}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: '#64748b', fontSize: 10 }}
              axisLine={{ stroke: 'rgba(148,163,184,0.1)' }}
              tickLine={false}
              allowDecimals={false}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              iconType="circle"
              iconSize={8}
              wrapperStyle={{ fontSize: '0.7rem', paddingTop: '8px' }}
              formatter={(value) => <span style={{ color: '#94a3b8' }}>{value.toUpperCase()}</span>}
            />
            {Object.entries(LANE_COLORS).map(([lane, color]) => (
              <Area
                key={lane}
                type="monotone"
                dataKey={lane}
                stroke={color}
                strokeWidth={2}
                fill={`url(#grad-${lane})`}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 2, fill: '#0a0e1a' }}
                animationDuration={300}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
