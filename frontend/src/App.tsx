import { useState, useEffect } from 'react';
import { Activity, Moon, Zap, TrendingUp, RefreshCw, Loader } from 'lucide-react';
import { RiskGauge } from './components/RiskGauge';
import { AlertPanel } from './components/AlertPanel';
import { BiometricChart } from './components/BiometricChart';
import { IOSCheckInForm } from './components/IOSCheckInForm';
import type { DailyMetric, Alert, ModelPrediction } from './types/ember';
import './App.css';

type ActiveMetric = 'hrv' | 'sleep' | 'readiness' | 'riskScore';
type View = 'form' | 'dashboard';

const API_BASE = 'http://localhost:8000';
const API_TOKEN = import.meta.env.VITE_EMBER_API_TOKEN ?? 'ember-local-dev-token';

interface DashboardData {
  metrics: DailyMetric[];
  alerts: Alert[];
  currentRisk: number;
  lastSync: string | null;
  summary: { date: string; summary: string } | null;
  modelPrediction: ModelPrediction | null;
}

function App() {
  const [view, setView] = useState<View>('form');
  const [activeMetric, setActiveMetric] = useState<ActiveMetric>('riskScore');
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboard = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/dashboard`, {
        headers: { Authorization: `Bearer ${API_TOKEN}` },
      });
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const json = await res.json();

      const metrics: DailyMetric[] = json.metrics.map((m: Record<string, unknown>) => ({
        date: String(m.date ?? '').slice(5),
        hrv: Number(m.hrv ?? 0),
        sleep: Number(m.sleep ?? 0),
        readiness: Number(m.readiness ?? 0),
        riskScore: Number(m.riskScore ?? 0),
      }));

      const alerts: Alert[] = (json.alerts as Record<string, unknown>[]).map((a) => ({
        id: String(a.id),
        timestamp: String(a.date),
        severity: (a.severity as 'low' | 'medium' | 'high') ?? 'low',
        message: String(a.message),
        metric: 'Daily Pattern',
        value: 0,
        threshold: 0,
        dismissed: false,
      }));

      setData({
        metrics,
        alerts,
        currentRisk: Number(json.currentRisk ?? 0),
        lastSync: json.lastSync ?? null,
        summary: json.summary ?? null,
        modelPrediction: json.modelPrediction ?? null,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  const latest = data?.metrics?.[data.metrics.length - 1];

  const metricTabs = latest ? [
    { key: 'hrv' as ActiveMetric, label: 'HRV', value: `${latest.hrv}`, icon: Activity, color: '#818cf8' },
    { key: 'sleep' as ActiveMetric, label: 'Sleep', value: `${latest.sleep}`, icon: Moon, color: '#34d399' },
    { key: 'readiness' as ActiveMetric, label: 'Readiness', value: `${latest.readiness}`, icon: Zap, color: '#60a5fa' },
    { key: 'riskScore' as ActiveMetric, label: 'Pattern', value: `${latest.riskScore}`, icon: TrendingUp, color: '#f87171' },
  ] : [];

  return (
    <div className="app" data-testid="ember-app">
      <header className="header" data-testid="header">
        <div className="logo">
          <div className="logo-mark" />
          <span className="logo-text">EMBER</span>
        </div>
        <div className="header-right">
          {data?.lastSync && view === 'dashboard' && (
            <div className="sync-info">
              <RefreshCw size={12} />
              <span>Synced {data.lastSync}</span>
            </div>
          )}
          {view === 'dashboard' && (
            <button className="refresh-btn" onClick={fetchDashboard} disabled={loading} aria-label="Refresh data">
              <RefreshCw size={14} className={loading ? 'spinning' : ''} />
            </button>
          )}
        </div>
      </header>
      <nav className="nav-tabs">
        <button className={`nav-tab${view === 'form' ? ' active' : ''}`} onClick={() => setView('form')} data-testid="tab-form">FORM</button>
        <button className={`nav-tab${view === 'dashboard' ? ' active' : ''}`} onClick={() => setView('dashboard')} data-testid="tab-dashboard">DASHBOARD</button>
      </nav>

      <main className="main">
        {view === 'form' && (
          <IOSCheckInForm
            modelPrediction={data?.modelPrediction ?? null}
            lastSync={data?.lastSync ?? null}
          />
        )}

        {view === 'dashboard' && loading && (
          <div className="loading-state" data-testid="loading">
            <Loader size={24} className="spinning" />
            <span>Loading EMBER data...</span>
          </div>
        )}

        {view === 'dashboard' && error && (
          <div className="error-state" data-testid="error">
            <span>⚠ {error}</span>
            <button onClick={fetchDashboard}>Retry</button>
          </div>
        )}

        {view === 'dashboard' && !loading && !error && data && (
          <>
            <div className="top-row">
              <div className="risk-card" data-testid="risk-card">
                <div className="card-label">DAILY SIGNAL</div>
                <RiskGauge score={data.currentRisk} />
                {data.summary && (
                  <p className="risk-caption">
                    {data.summary.summary.match(/\*\*Overall Signal: (.+?)\*\*/)?.[1] ?? 'No signal'}
                  </p>
                )}
              </div>
              <AlertPanel alerts={data.alerts} />
            </div>

            {data.metrics.length > 0 && (
              <div className="chart-card" data-testid="chart-card">
                <div className="metric-tabs" data-testid="metric-tabs">
                  {metricTabs.map(tab => {
                    const Icon = tab.icon;
                    return (
                      <button
                        key={tab.key}
                        className={`metric-tab ${activeMetric === tab.key ? 'active' : ''}`}
                        data-testid={`tab-${tab.key}`}
                        onClick={() => setActiveMetric(tab.key)}
                        style={activeMetric === tab.key ? { borderColor: tab.color, color: tab.color } : {}}
                      >
                        <Icon size={14} />
                        <span>{tab.label}</span>
                        <strong>{tab.value}</strong>
                      </button>
                    );
                  })}
                </div>
                <BiometricChart metrics={data.metrics} activeMetric={activeMetric} />
              </div>
            )}

            {data.summary && (
              <div className="summary-card" data-testid="summary-card">
                <div className="card-label">YOUR SUMMARY — {data.summary.date}</div>
                <p className="summary-text">{data.summary.summary.replace(/\*\*/g, '')}</p>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

export default App;