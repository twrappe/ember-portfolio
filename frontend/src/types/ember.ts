export interface DailyMetric {
  date: string;
  hrv: number;
  sleep: number;       // hours
  readiness: number;   // 0-100
  riskScore: number;   // 0-100, composite deviation score
}

export interface Alert {
  id: string;
  timestamp: string;
  severity: 'low' | 'medium' | 'high';
  message: string;
  metric: string;
  value: number;
  threshold: number;
  dismissed: boolean;
}

export interface EmberState {
  metrics: DailyMetric[];
  alerts: Alert[];
  currentRisk: number;
  lastSync: string;
}

export interface ModelPrediction {
  day: string;
  prediction: 'BASELINE' | 'ELEVATED' | string;
  p_elevated: number;
  model: string;
  explanation?: {
    feature: string;
    raw: number;
    z: number;
    coef: number;
    contribution: number;
    direction: 'toward_elevated' | 'toward_baseline';
  }[];
}
