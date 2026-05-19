# Visual Project Blueprint

## Purpose
This is the graphical, big-picture guide for the full project.
Use this document when onboarding developers, reviewing architecture, and planning safe changes.

## 1. System At A Glance

```mermaid
flowchart LR
  subgraph Sources[External Sources]
    WN[Whatnot Livestream DOM]
    USER[Dashboard Users]
  end

  subgraph CollectorLayer[Collector Layer]
    C1[src/collector/main.py]
    C2[Playwright Browser Sessions]
  end

  subgraph ApiLayer[API and Business Layer]
    L1[Legacy Runtime server/api.py]
    F1[FastAPI app/main.py]
    BIZ[Business Services and Repositories]
  end

  subgraph DataLayer[Data Layer]
    SQL[SQLite whatnot.db and events]
    PG[Postgres Sidecar sqlite_mirror schema]
    REDIS[Redis Sidecar Cache]
    JSON[JSON Runtime State Files]
  end

  subgraph FrontendLayer[Frontend Layer]
    UI[dashboard-vite React App]
    OP[Operator and Scanner Views]
    CO[Company and Analytics Views]
  end

  WN --> C2 --> C1 --> SQL
  USER --> UI --> OP
  USER --> UI --> CO

  UI --> L1
  UI --> F1

  L1 --> BIZ --> SQL
  F1 --> BIZ --> SQL

  SQL --> PG
  SQL --> REDIS
  L1 --> JSON
  C1 --> JSON
```

## 2. Runtime Modes

```mermaid
flowchart TD
  START[Start Runtime]
  START --> MODE{Which Mode?}

  MODE --> LIVE[Live Collector]
  MODE --> SPEC[Spectator Collector]

  LIVE --> LIVESESSION[Bind or create company_session]
  LIVESESSION --> LIVEEVENTS[Write stream events]

  SPEC --> SPECEVENTS[Write competitor events]

  LIVEEVENTS --> EVENTSDB[(events and company tables)]
  SPECEVENTS --> EVENTSDB

  EVENTSDB --> APIREADS[API reads and business transforms]
  APIREADS --> DASH[Dashboard updates]
```

## 3. Request Lifecycle

```mermaid
sequenceDiagram
  participant U as Browser User
  participant R as React View
  participant A as API Route
  participant S as Service/DB Layer
  participant D as SQLite/Postgres

  U->>R: Open page or action
  R->>A: HTTP request (cookie + csrf)
  A->>S: Validate auth, run business logic
  S->>D: Query or write
  D-->>S: Data rows
  S-->>A: Structured response
  A-->>R: JSON payload
  R-->>U: Updated UI state
```

## 4. Backend Responsibility Map

```mermaid
flowchart LR
  API[server/api.py route transport]
  CDB[server/company_db.py business persistence]
  EDB[server/events_db.py raw event interpretation]
  AUTH[server/auth.py sessions and access]
  CM[server/collector_manager.py collector orchestration]
  STATE[server/state.py json runtime state]
  CFG[server/config.py env and path config]

  API --> CDB
  API --> EDB
  API --> AUTH
  API --> CM
  API --> STATE
  API --> CFG
```

## 5. Frontend Route Map

```mermaid
flowchart TD
  APP[src/App.jsx]

  APP --> TV[/]
  APP --> OP[/operator]
  APP --> TVS[/operator/tv-scanner]
  APP --> WS[/operator/winner-scanner]
  APP --> OBS[/operator/obs]
  APP --> SES[/session]
  APP --> CO[/company]

  CO --> INV[Inventory tabs]
  CO --> ORD[Orders and sessions]
  CO --> ANA[Analytics panels]
```

## 6. Data Truth Hierarchy

```mermaid
flowchart TD
  E[Collector Raw Events]
  C[Company Business Tables]
  O[Sale Orders and Auction Results]
  V[Dashboard Views]

  E --> C
  C --> O
  O --> V

  note1[Browser localStorage and sessionStorage improve UX but are not source of truth]
  V -. ui cache only .-> note1
```

## 7. PostgreSQL Migration Topology

```mermaid
flowchart LR
  SQLITE[(SQLite Primary Today)] --> SIDECAR[Sidecar Sync Process]
  SIDECAR --> PGT[(Postgres sqlite_mirror)]
  SIDECAR --> RDS[(Redis Sidecar)]

  PGT --> CUT{Domain Cutover Flags}
  CUT --> READPG[Read from Postgres domain]
  CUT --> WRITEPG[Write to Postgres domain]

  SQLITE --> LEGACY[Legacy fallback paths]
```

## 8. Local Bootstrap Flow (After Clone)

```mermaid
flowchart TD
  CLONE[git clone]
  CLONE --> RUN[Run scripts/bootstrap_postgres_clone.sh]
  RUN --> DOCKER[Start Postgres container on 5433]
  RUN --> ENV[Update local .env sidecar DSN]
  RUN --> SCHEMA[Run ensure_wave1_postgres_schema]
  RUN --> SEED{SEED_DEMO default 1}
  SEED -->|1| DEMO[Apply schema and demo SQL]
  SEED -->|0| SKIP[Skip demo seed]
  DEMO --> READY[Local database ready]
  SKIP --> READY
```

## 9. Developer Git Flow

```mermaid
gitGraph
  commit id: "main stable"
  branch dev
  checkout dev
  commit id: "feature integration"
  commit id: "qa fixes"
  checkout main
  merge dev id: "tested merge"
```

Policy:
- Developers push feature work to dev via merge requests.
- QA and acceptance happen on dev.
- Only tested changes are merged from dev into main.

## 10. High-Risk Change Zones

```mermaid
flowchart LR
  RISK1[server/api.py route contracts]
  RISK2[server/company_db.py data mutation logic]
  RISK3[src/collector parsing selectors]
  RISK4[dashboard-vite polling and scanner flows]
  RISK5[auth session and csrf handling]

  RISK1 --> IMPACT[Regression risk: user-visible breakage]
  RISK2 --> IMPACT
  RISK3 --> IMPACT
  RISK4 --> IMPACT
  RISK5 --> IMPACT
```

## 11. First-Day Read Path For Developers

1. README overview and run commands.
2. This visual blueprint for system map.
3. technical_architecture.md for component depth.
4. backend_architecture.md and frontend_architecture.md for ownership boundaries.
5. testing_guide.md before making any feature changes.

## 12. Quick Command Sheet

From whatnot-collector:

- Start API:
  - `uvicorn app.main:app --host 0.0.0.0 --port 8088`
- Start frontend:
  - `cd dashboard-vite && npm run dev`
- Postgres bootstrap:
  - `./scripts/bootstrap_postgres_clone.sh`
- API profiling:
  - `./.venv/bin/python tools/profile_dashboard_api.py --base-url http://127.0.0.1:8088 --path /api/company/intelligence --rounds 3`

## 13. Related Documents

- technical_architecture.md
- backend_architecture.md
- frontend_architecture.md
- api_reference.md
- database_schema_reference.md
- sidecar_mirror_guide.md
- postgres_primary_cutover_plan.md
