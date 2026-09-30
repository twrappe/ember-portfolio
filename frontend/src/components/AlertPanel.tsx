import { useState } from 'react';
import { X, AlertTriangle, AlertCircle, Info } from 'lucide-react';
import type { Alert } from '../types/ember';

interface AlertPanelProps {
  alerts: Alert[];
}

const severityConfig = {
  high: { icon: AlertCircle, color: '#f87171', bg: 'rgba(248,113,113,0.08)', border: 'rgba(248,113,113,0.25)', label: 'TAKE ACTION' },
  medium: { icon: AlertTriangle, color: '#fb923c', bg: 'rgba(251,146,60,0.08)', border: 'rgba(251,146,60,0.25)', label: 'HEADS UP' },
  low: { icon: Info, color: '#60a5fa', bg: 'rgba(96,165,250,0.08)', border: 'rgba(96,165,250,0.25)', label: 'FYI' },
};

export function AlertPanel({ alerts }: AlertPanelProps) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const visible = alerts.filter(a => !dismissed.has(a.id));

  const formatTime = (ts: string) => {
    return new Date(ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="alert-panel" data-testid="alert-panel">
      <div className="panel-header">
        <span className="panel-label">NOTICES</span>
        {visible.length > 0 && (
          <span className="alert-badge" data-testid="alert-count">{visible.length}</span>
        )}
      </div>

      {visible.length === 0 ? (
        <div className="no-alerts" data-testid="no-alerts">
          <span>Nothing to flag</span>
        </div>
      ) : (
        <div className="alert-list">
          {visible.map(alert => {
            const cfg = severityConfig[alert.severity];
            const Icon = cfg.icon;
            return (
              <div
                key={alert.id}
                className="alert-item"
                data-testid={`alert-${alert.id}`}
                data-severity={alert.severity}
                style={{ background: cfg.bg, borderColor: cfg.border }}
              >
                <Icon size={16} color={cfg.color} style={{ flexShrink: 0, marginTop: 2 }} />
                <div className="alert-content">
                  <div className="alert-meta">
                    <span className="alert-severity" style={{ color: cfg.color }}>{cfg.label}</span>
                    <span className="alert-time">{formatTime(alert.timestamp)}</span>
                  </div>
                  <p className="alert-message">{alert.message}</p>
                  <div className="alert-metric">
                    {alert.metric}: <strong style={{ color: cfg.color }}>{alert.value}</strong>
                    <span className="alert-threshold"> (threshold: {alert.threshold})</span>
                  </div>
                </div>
                <button
                  className="dismiss-btn"
                  onClick={() => setDismissed(prev => new Set([...prev, alert.id]))}
                  aria-label="Dismiss alert"
                  data-testid={`dismiss-${alert.id}`}
                >
                  <X size={14} />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
