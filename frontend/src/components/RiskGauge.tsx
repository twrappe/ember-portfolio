import { useEffect, useState } from 'react';

interface RiskGaugeProps {
  score: number; // 0-100
}

export function RiskGauge({ score }: RiskGaugeProps) {
  const [animated, setAnimated] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => setAnimated(score), 300);
    return () => clearTimeout(timer);
  }, [score]);

  const radius = 80;
  const stroke = 10;
  const normalizedRadius = radius - stroke;
  const circumference = normalizedRadius * 2 * Math.PI;
  const strokeDashoffset = circumference - (animated / 100) * circumference * 0.75;
  const rotation = -135;

  const getColor = (s: number) => {
    if (s < 30) return '#4ade80';
    if (s < 60) return '#facc15';
    if (s < 80) return '#fb923c';
    return '#f87171';
  };

  const getLabel = (s: number) => {
    if (s < 30) return 'ON TRACK';
    if (s < 60) return 'HEADS UP';
    if (s < 80) return 'CHECK IN';
    return 'TAKE ACTION';
  };

  const color = getColor(score);

  return (
    <div className="risk-gauge" data-testid="risk-gauge">
      <svg width={radius * 2} height={radius * 1.6} viewBox={`0 0 ${radius * 2} ${radius * 1.6}`}>
        {/* Background arc */}
        <circle
          cx={radius}
          cy={radius}
          r={normalizedRadius}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={stroke}
          strokeDasharray={`${circumference * 0.75} ${circumference}`}
          strokeDashoffset={0}
          strokeLinecap="round"
          transform={`rotate(${rotation} ${radius} ${radius})`}
        />
        {/* Score arc */}
        <circle
          cx={radius}
          cy={radius}
          r={normalizedRadius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeDasharray={`${circumference * 0.75} ${circumference}`}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          transform={`rotate(${rotation} ${radius} ${radius})`}
          style={{
            transition: 'stroke-dashoffset 1.2s cubic-bezier(0.34, 1.56, 0.64, 1), stroke 0.6s ease',
            filter: `drop-shadow(0 0 8px ${color}88)`,
          }}
        />
        <text x={radius} y={radius + 8} textAnchor="middle" fill={color} fontSize="32" fontWeight="700" fontFamily="'DM Mono', monospace">
          {animated}
        </text>
        <text x={radius} y={radius + 28} textAnchor="middle" fill="rgba(255,255,255,0.4)" fontSize="10" fontFamily="'DM Mono', monospace" letterSpacing="3">
          {getLabel(score)}
        </text>
      </svg>
    </div>
  );
}
