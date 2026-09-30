# EMBER System Diagram (model branch)

Source of truth for this diagram:
- Branch: model
- Scope: files currently present in this branch

## End-to-End Runtime Flow

```mermaid
flowchart LR
    U[User] -->|OAuth setup one time| AUTH[auth.py]
    AUTH --> ENV[.env tokens]

    subgraph PIPE[Daily Pipeline via run_ember.py]
      RUN[run_ember.py]
      PULL[pull_data.py]
      SCORE[score_baseline.py]
      SUM[summarize.py]
      MLOG[model_logreg.py]
    end

    RUN --> PULL
    RUN --> SCORE
    RUN --> SUM
    RUN --> MLOG

    PULL --> TM[token_manager.py]
    TM --> ENV
    PULL -->|readiness sleep endpoints| OURA[(Oura API v2)]
    PULL --> DR[(data/daily_readiness.csv)]
    PULL --> DS[(data/daily_sleep.csv)]

    SCORE --> DR
    SCORE --> DD[(data/deviation_scores.csv)]

    SUM --> DD
    SUM --> ML[(data/mood_log.csv)]
    SUM -->|summary generation| CLAUDE[(Anthropic API)]
    SUM --> SJ[(data/summaries.jsonl)]

    MLOG --> DR
    MLOG --> DS
    MLOG --> DD
    MLOG --> ML
    MLOG --> JOB[(models/logreg_stress.joblib)]

    subgraph SERVE[Serving Layer]
      API[api.py on :8000]
      MOOD[mood_server.py on :8001]
      FE[frontend React Vite on :5173]
    end

    DR --> API
    DS --> API
    DD --> API
    SJ --> API

    U --> FE
    FE -->|GET /api/dashboard| API

    U -->|Morning evening check-ins| MOOD
    MOOD --> ML
```

## Model Export Flow (branch-specific)

```mermaid
flowchart LR
    JOB[(models/logreg_stress.joblib)] --> XONNX[export_onnx.py]
    XONNX --> ONNX[(models/logreg_stress.onnx)]
    ONNX --> TRT[Optional TensorRT INT8 engine build]
```

## Runtime Boundaries

- External dependencies:
  - Oura OAuth and usercollection APIs
  - Anthropic messages API
- Local persistence:
  - data directory CSV and JSONL files
  - logs/ember.log
  - .env token and key material
  - models artifacts in models/
- Local services:
  - Dashboard API on 8000
  - Mood service on 8001
  - Frontend dev server on 5173
