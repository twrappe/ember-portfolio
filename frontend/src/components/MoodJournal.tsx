import { useState } from 'react';
import { CheckCircle, AlertCircle } from 'lucide-react';

const MOOD_API = 'http://localhost:8001';
const TODAY = new Date().toISOString().split('T')[0];

const MORNING_REQUIRED = [
  'rested', 'early_waking', 'less_sleep_fine',
  'thought_speed_morning', 'classification_night',
];
const EVENING_REQUIRED = [
  'energy', 'new_projects', 'effortful', 'concentration',
  'mood', 'irritable', 'impulsive', 'withdrew',
  'alcohol', 'illness', 'travel', 'life_stress', 'classification_day',
];

// ---------------------------------------------------------------------------
// Primitive input components
// ---------------------------------------------------------------------------

function Scale({
  value, hints, onChange,
}: {
  value: number | undefined;
  hints: [string, string];
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="jnl-scale-row">
        {[1, 2, 3, 4, 5].map(n => (
          <button
            key={n}
            type="button"
            className={`jnl-scale-btn${value === n ? ' selected' : ''}`}
            onClick={() => onChange(n)}
          >
            {n}
          </button>
        ))}
      </div>
      <div className="jnl-scale-hints">
        <span>{hints[0]}</span>
        <span>{hints[1]}</span>
      </div>
    </div>
  );
}

function YN({ value, onChange }: { value: string | undefined; onChange: (v: string) => void }) {
  return (
    <div className="jnl-yn-row">
      {['Yes', 'No'].map(opt => (
        <button
          key={opt}
          type="button"
          className={`jnl-yn-btn${value === opt ? ' selected' : ''}`}
          onClick={() => onChange(opt)}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

function Pills({
  options, value, onChange,
}: {
  options: string[];
  value: string | undefined;
  onChange: (v: string) => void;
}) {
  return (
    <div className="jnl-pills-row">
      {options.map(opt => (
        <button
          key={opt}
          type="button"
          className={`jnl-pill-btn${value === opt ? ' selected' : ''}`}
          onClick={() => onChange(opt)}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

function ClassGrid({
  options, value, onChange,
}: {
  options: string[];
  value: string | undefined;
  onChange: (v: string) => void;
}) {
  return (
    <div className="jnl-class-grid">
      {options.map(opt => (
        <button
          key={opt}
          type="button"
          className={`jnl-class-btn${value === opt ? ' selected' : ''}`}
          onClick={() => onChange(opt)}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Layout wrappers
// ---------------------------------------------------------------------------

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="jnl-section">
      <span className="card-label">{label}</span>
      <div className="jnl-card">{children}</div>
    </div>
  );
}

function Question({ label, optional, children }: { label: string; optional?: boolean; children: React.ReactNode }) {
  return (
    <div className="jnl-question">
      <div className="jnl-q-label">
        {label}
        {optional && <span className="jnl-optional"> — optional</span>}
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

type Session = 'morning' | 'evening';
type FieldMap = Record<string, string | number>;

export function MoodJournal() {
  const [date, setDate] = useState(TODAY);
  const [session, setSession] = useState<Session>('evening');
  const [fields, setFields] = useState<FieldMap>({});
  const [notes, setNotes] = useState('');
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle');
  const [statusMsg, setStatusMsg] = useState('');

  const set = (key: string, val: string | number) =>
    setFields(prev => ({ ...prev, [key]: val }));

  const reset = () => { setFields({}); setNotes(''); };

  const isToday = date === TODAY;
  const required = session === 'morning' ? MORNING_REQUIRED : EVENING_REQUIRED;
  const missing = required.filter(k => fields[k] === undefined);

  async function submit() {
    if (missing.length > 0) {
      setStatus('error');
      setStatusMsg(`Missing: ${missing[0].replace(/_/g, ' ')}`);
      setTimeout(() => setStatus('idle'), 3000);
      return;
    }

    setStatus('submitting');

    const payload: FieldMap = session === 'evening'
      ? { ...fields, notes }
      : { ...fields };

    const endpoint = isToday
      ? `/submit/${session}`
      : `/submit/backfill/${session}`;

    const body = isToday ? payload : { ...payload, date };

    try {
      const res = await fetch(`${MOOD_API}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const json = await res.json();
      if (res.ok) {
        setStatus('success');
        setStatusMsg('Logged');
        reset();
      } else {
        setStatus('error');
        setStatusMsg(json.message ?? 'Server error');
      }
    } catch {
      setStatus('error');
      setStatusMsg('Mood server unreachable — run: uvicorn mood_server:app --port 8001');
    }

    setTimeout(() => setStatus('idle'), 4000);
  }

  return (
    <div className="jnl-root">

      {/* ── Date + session picker ── */}
      <div className="jnl-controls">
        <div className="jnl-control-group">
          <span className="card-label">DATE</span>
          <input
            type="date"
            className="jnl-date-input"
            value={date}
            max={TODAY}
            onChange={e => { setDate(e.target.value); reset(); }}
          />
        </div>
        <div className="jnl-control-group">
          <span className="card-label">SESSION</span>
          <div className="jnl-session-toggle">
            {(['morning', 'evening'] as const).map(s => (
              <button
                key={s}
                type="button"
                className={`jnl-session-btn${session === s ? ' active' : ''}`}
                onClick={() => { setSession(s); reset(); }}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Morning form ── */}
      {session === 'morning' && (
        <>
          <Section label="SLEEP">
            <Question label="Did you feel rested when you woke up?">
              <Scale value={fields.rested as number} hints={['not at all', 'completely']} onChange={v => set('rested', v)} />
            </Question>
            <Question label="Woke up earlier than intended and couldn't go back to sleep?">
              <YN value={fields.early_waking as string} onChange={v => set('early_waking', v)} />
            </Question>
            <Question label="Needed less sleep than usual but still felt fine?">
              <YN value={fields.less_sleep_fine as string} onChange={v => set('less_sleep_fine', v)} />
            </Question>
          </Section>

          <Section label="COGNITION">
            <Question label="Thought speed this morning">
              <Scale value={fields.thought_speed_morning as number} hints={['foggy', 'racing']} onChange={v => set('thought_speed_morning', v)} />
            </Question>
          </Section>

          <Section label="OVERALL">
            <Question label="How would you classify last night?">
              <ClassGrid
                options={['Great', 'Restful', 'Restless', 'Very poor']}
                value={fields.classification_night as string}
                onChange={v => set('classification_night', v)}
              />
            </Question>
          </Section>
        </>
      )}

      {/* ── Evening form ── */}
      {session === 'evening' && (
        <>
          <Section label="ENERGY & ACTIVITY">
            <Question label="Overall energy level today">
              <Scale value={fields.energy as number} hints={['very low', 'very high']} onChange={v => set('energy', v)} />
            </Question>
            <Question label="Started new projects or had an unusual number of ideas?">
              <YN value={fields.new_projects as string} onChange={v => set('new_projects', v)} />
            </Question>
            <Question label="Did everything feel effortful today?">
              <YN value={fields.effortful as string} onChange={v => set('effortful', v)} />
            </Question>
          </Section>

          <Section label="COGNITION">
            <Question label="Concentration today">
              <Scale value={fields.concentration as number} hints={['very poor', 'sharp']} onChange={v => set('concentration', v)} />
            </Question>
          </Section>

          <Section label="MOOD & BEHAVIOR">
            <Question label="Overall mood today">
              <Scale value={fields.mood as number} hints={['very low', 'very elevated']} onChange={v => set('mood', v)} />
            </Question>
            <Question label="More irritable than usual?">
              <YN value={fields.irritable as string} onChange={v => set('irritable', v)} />
            </Question>
            <Question label="Made any impulsive decisions?">
              <YN value={fields.impulsive as string} onChange={v => set('impulsive', v)} />
            </Question>
            <Question label="Socially withdrew today?">
              <YN value={fields.withdrew as string} onChange={v => set('withdrew', v)} />
            </Question>
          </Section>

          <Section label="CONFOUNDERS">
            <Question label="Alcohol today?">
              <Pills options={['None', '1 drink', '2 drinks', '3+']} value={fields.alcohol as string} onChange={v => set('alcohol', v)} />
            </Question>
            <Question label="Illness or physical stress?">
              <YN value={fields.illness as string} onChange={v => set('illness', v)} />
            </Question>
            <Question label="Travel or major schedule disruption?">
              <YN value={fields.travel as string} onChange={v => set('travel', v)} />
            </Question>
            <Question label="Unusually high life stress?">
              <YN value={fields.life_stress as string} onChange={v => set('life_stress', v)} />
            </Question>
          </Section>

          <Section label="CLASSIFICATION">
            <Question label="How would you classify today?">
              <ClassGrid
                options={['Euthymic', 'Mildly elevated', 'Elevated', 'Mildly depressed', 'Depressed']}
                value={fields.classification_day as string}
                onChange={v => set('classification_day', v)}
              />
            </Question>
            <Question label="Anything notable to flag?" optional>
              <textarea
                className="jnl-textarea"
                placeholder="free text..."
                value={notes}
                rows={3}
                onChange={e => setNotes(e.target.value)}
              />
            </Question>
          </Section>
        </>
      )}

      {/* ── Status + submit ── */}
      {(status === 'error' || status === 'success') && (
        <div className={`jnl-status ${status}`}>
          {status === 'error'
            ? <AlertCircle size={14} />
            : <CheckCircle size={14} />}
          <span>{statusMsg}</span>
        </div>
      )}

      <button
        type="button"
        className="jnl-submit-btn"
        disabled={status === 'submitting'}
        onClick={submit}
      >
        {status === 'submitting'
          ? 'LOGGING...'
          : `LOG ${session.toUpperCase()}${!isToday ? ' — BACKFILL' : ''}`}
      </button>
    </div>
  );
}
