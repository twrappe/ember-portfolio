import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { ModelPrediction } from '../types/ember';

const MOOD_API = 'http://localhost:8001';
const TODAY = new Date().toISOString().split('T')[0];

type Session = 'morning' | 'evening';
type FormValues = Record<string, string>;

interface IOSCheckInFormProps {
  modelPrediction: ModelPrediction | null;
  lastSync: string | null;
}

const REQUIRED: Record<Session, string[]> = {
  morning: ['rested', 'early_waking', 'less_sleep_fine', 'thought_speed_morning', 'classification_night'],
  evening: [
    'energy',
    'new_projects',
    'effortful',
    'concentration',
    'mood',
    'irritable',
    'impulsive',
    'withdrew',
    'alcohol',
    'illness',
    'travel',
    'life_stress',
    'classification_day',
  ],
};

const SCALE = ['1', '2', '3', '4', '5'];
const YES_NO = ['Yes', 'No'];

function Field({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="ios-field" data-testid={`field-${id}`}>
      <label htmlFor={id} className="ios-label">{label}</label>
      {children}
    </div>
  );
}

export function IOSCheckInForm({ modelPrediction, lastSync }: IOSCheckInFormProps) {
  const [session, setSession] = useState<Session>('evening');
  const [date, setDate] = useState(TODAY);
  const [values, setValues] = useState<FormValues>({});
  const [status, setStatus] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const required = useMemo(() => REQUIRED[session], [session]);

  const setValue = (key: string, value: string) => {
    setValues((prev) => ({ ...prev, [key]: value }));
  };

  const resetSessionFields = () => {
    setValues({});
    setStatus('');
  };

  const toPayload = () => {
    const base = { ...values };
    const numericKeys = session === 'morning'
      ? ['rested', 'thought_speed_morning']
      : ['energy', 'concentration', 'mood'];

    for (const key of numericKeys) {
      if (base[key]) {
        base[key] = String(Number(base[key]));
      }
    }

    return {
      ...base,
      ...(session === 'evening' ? { notes: values.notes ?? '' } : {}),
    };
  };

  const submit = async () => {
    const missing = required.find((key) => !values[key]);
    if (missing) {
      setStatus(`Missing required field: ${missing}`);
      return;
    }

    const isToday = date === TODAY;
    const endpoint = isToday ? `/submit/${session}` : `/submit/backfill/${session}`;
    const payload = toPayload();
    const body = isToday ? payload : { ...payload, date };

    setIsSubmitting(true);
    setStatus('Submitting...');

    try {
      const res = await fetch(`${MOOD_API}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      const json = await res.json();
      if (!res.ok) {
        setStatus(json.message ?? 'Submission failed');
        return;
      }

      setStatus('Saved successfully');
      setValues({});
    } catch {
      setStatus('Mood API unreachable. Start mood_server on :8001');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form className="ios-form" data-testid="ios-checkin-form" onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <section className="ios-card" data-testid="ml-signal-card">
        <h2 className="ios-title">Daily ML Signal</h2>
        <div className="ios-grid">
          <Field id="ml-day" label="Prediction Day">
            <input id="ml-day" name="ml-day" readOnly value={modelPrediction?.day ?? '-'} />
          </Field>
          <Field id="ml-prediction" label="Model Prediction">
            <input id="ml-prediction" name="ml-prediction" readOnly value={modelPrediction?.prediction ?? 'Not available'} />
          </Field>
          <Field id="ml-probability" label="P Elevated">
            <input id="ml-probability" name="ml-probability" readOnly value={modelPrediction ? String(modelPrediction.p_elevated) : '-'} />
          </Field>
          <Field id="last-sync" label="Last Sync">
            <input id="last-sync" name="last-sync" readOnly value={lastSync ?? '-'} />
          </Field>
        </div>
      </section>

      <section className="ios-card" data-testid="checkin-card">
        <h2 className="ios-title">Daily Check-In</h2>
        <div className="ios-grid ios-grid-2">
          <Field id="entry-date" label="Date">
            <input
              id="entry-date"
              name="entry-date"
              type="date"
              value={date}
              max={TODAY}
              onChange={(e) => setDate(e.target.value)}
            />
          </Field>
          <Field id="entry-session" label="Session">
            <select
              id="entry-session"
              name="entry-session"
              value={session}
              onChange={(e) => {
                setSession(e.target.value as Session);
                resetSessionFields();
              }}
            >
              <option value="morning">morning</option>
              <option value="evening">evening</option>
            </select>
          </Field>
        </div>

        {session === 'morning' && (
          <div className="ios-grid" data-testid="morning-fields">
            <Field id="rested" label="Rested (1-5)">
              <select id="rested" name="rested" value={values.rested ?? ''} onChange={(e) => setValue('rested', e.target.value)}>
                <option value="">Select</option>
                {SCALE.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="early_waking" label="Early waking">
              <select id="early_waking" name="early_waking" value={values.early_waking ?? ''} onChange={(e) => setValue('early_waking', e.target.value)}>
                <option value="">Select</option>
                {YES_NO.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="less_sleep_fine" label="Less sleep but felt fine">
              <select id="less_sleep_fine" name="less_sleep_fine" value={values.less_sleep_fine ?? ''} onChange={(e) => setValue('less_sleep_fine', e.target.value)}>
                <option value="">Select</option>
                {YES_NO.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="thought_speed_morning" label="Thought speed (1-5)">
              <select id="thought_speed_morning" name="thought_speed_morning" value={values.thought_speed_morning ?? ''} onChange={(e) => setValue('thought_speed_morning', e.target.value)}>
                <option value="">Select</option>
                {SCALE.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="classification_night" label="Night classification">
              <select id="classification_night" name="classification_night" value={values.classification_night ?? ''} onChange={(e) => setValue('classification_night', e.target.value)}>
                <option value="">Select</option>
                <option value="Great">Great</option>
                <option value="Restful">Restful</option>
                <option value="Restless">Restless</option>
                <option value="Very poor">Very poor</option>
              </select>
            </Field>
          </div>
        )}

        {session === 'evening' && (
          <div className="ios-grid" data-testid="evening-fields">
            <Field id="energy" label="Energy (1-5)">
              <select id="energy" name="energy" value={values.energy ?? ''} onChange={(e) => setValue('energy', e.target.value)}>
                <option value="">Select</option>
                {SCALE.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="new_projects" label="New projects or many ideas">
              <select id="new_projects" name="new_projects" value={values.new_projects ?? ''} onChange={(e) => setValue('new_projects', e.target.value)}>
                <option value="">Select</option>
                {YES_NO.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="effortful" label="Day felt effortful">
              <select id="effortful" name="effortful" value={values.effortful ?? ''} onChange={(e) => setValue('effortful', e.target.value)}>
                <option value="">Select</option>
                {YES_NO.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="concentration" label="Concentration (1-5)">
              <select id="concentration" name="concentration" value={values.concentration ?? ''} onChange={(e) => setValue('concentration', e.target.value)}>
                <option value="">Select</option>
                {SCALE.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="mood" label="Mood (1-5)">
              <select id="mood" name="mood" value={values.mood ?? ''} onChange={(e) => setValue('mood', e.target.value)}>
                <option value="">Select</option>
                {SCALE.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="irritable" label="More irritable">
              <select id="irritable" name="irritable" value={values.irritable ?? ''} onChange={(e) => setValue('irritable', e.target.value)}>
                <option value="">Select</option>
                {YES_NO.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="impulsive" label="Impulsive decisions">
              <select id="impulsive" name="impulsive" value={values.impulsive ?? ''} onChange={(e) => setValue('impulsive', e.target.value)}>
                <option value="">Select</option>
                {YES_NO.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="withdrew" label="Social withdrawal">
              <select id="withdrew" name="withdrew" value={values.withdrew ?? ''} onChange={(e) => setValue('withdrew', e.target.value)}>
                <option value="">Select</option>
                {YES_NO.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="alcohol" label="Alcohol">
              <select id="alcohol" name="alcohol" value={values.alcohol ?? ''} onChange={(e) => setValue('alcohol', e.target.value)}>
                <option value="">Select</option>
                <option value="None">None</option>
                <option value="1 drink">1 drink</option>
                <option value="2 drinks">2 drinks</option>
                <option value="3+">3+</option>
              </select>
            </Field>
            <Field id="illness" label="Illness">
              <select id="illness" name="illness" value={values.illness ?? ''} onChange={(e) => setValue('illness', e.target.value)}>
                <option value="">Select</option>
                {YES_NO.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="travel" label="Travel disruption">
              <select id="travel" name="travel" value={values.travel ?? ''} onChange={(e) => setValue('travel', e.target.value)}>
                <option value="">Select</option>
                {YES_NO.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="life_stress" label="High life stress">
              <select id="life_stress" name="life_stress" value={values.life_stress ?? ''} onChange={(e) => setValue('life_stress', e.target.value)}>
                <option value="">Select</option>
                {YES_NO.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Field>
            <Field id="classification_day" label="Day classification">
              <select id="classification_day" name="classification_day" value={values.classification_day ?? ''} onChange={(e) => setValue('classification_day', e.target.value)}>
                <option value="">Select</option>
                <option value="Euthymic">Euthymic</option>
                <option value="Mildly elevated">Mildly elevated</option>
                <option value="Elevated">Elevated</option>
                <option value="Mildly depressed">Mildly depressed</option>
                <option value="Depressed">Depressed</option>
              </select>
            </Field>
            <Field id="notes" label="Notes (optional)">
              <textarea id="notes" name="notes" rows={3} value={values.notes ?? ''} onChange={(e) => setValue('notes', e.target.value)} />
            </Field>
          </div>
        )}

        <button
          type="submit"
          className="ios-submit"
          data-testid="submit-checkin"
          disabled={isSubmitting}
          aria-label="Submit checkin"
        >
          {isSubmitting ? 'Submitting...' : `Submit ${session} check-in`}
        </button>

        {status && <p className="ios-status" data-testid="form-status">{status}</p>}
      </section>
    </form>
  );
}
