import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import type { DailyMetric } from '../types/ember';

interface BiometricChartProps {
  metrics: DailyMetric[];
  activeMetric: 'hrv' | 'sleep' | 'readiness' | 'riskScore';
}

const metricConfig = {
  hrv: { label: 'HRV', unit: 'ms', color: '#818cf8', domain: [0, 80] },
  sleep: { label: 'Sleep', unit: 'h', color: '#34d399', domain: [0, 10] },
  readiness: { label: 'Readiness', unit: '', color: '#60a5fa', domain: [0, 100] },
  riskScore: { label: 'Pattern', unit: '', color: '#f87171', domain: [0, 100] },
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const { color, unit } = metricConfig[payload[0].name as keyof typeof metricConfig] ?? { color: '#fff', unit: '' };
  return (
    <div className="chart-tooltip">
      <div className="tooltip-date">{label}</div>
      <div className="tooltip-value" style={{ color }}>
        {payload[0].value}{unit}
      </div>
    </div>
  );
};

export function BiometricChart({ metrics, activeMetric }: BiometricChartProps) {
  const cfg = metricConfig[activeMetric];

  return (
    <div className="chart-container" data-testid="biometric-chart" data-metric={activeMetric}>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={metrics} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis
            dataKey="date"
            tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11, fontFamily: "'DM Mono', monospace" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={cfg.domain as [number, number]}
            tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11, fontFamily: "'DM Mono', monospace" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Line
            type="monotone"
            dataKey={activeMetric}
            name={activeMetric}
            stroke={cfg.color}
            strokeWidth={2}
            dot={{ fill: cfg.color, r: 3, strokeWidth: 0 }}
            activeDot={{ r: 5, fill: cfg.color, filter: `drop-shadow(0 0 6px ${cfg.color})` }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
