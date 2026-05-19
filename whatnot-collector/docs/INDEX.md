# Documentation Index

## Start Here

If you are new to the project, read these first:

1. [README.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/README.md)
2. [visual_project_blueprint.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/visual_project_blueprint.md)
3. [intern_handbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/intern_handbook.md)
4. [technical_architecture.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/technical_architecture.md)
5. [contribution_safety_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/contribution_safety_guide.md)

## Onboarding And Project Understanding

- [visual_project_blueprint.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/visual_project_blueprint.md)
  - graphical architecture and runtime overview
  - fastest way to build a shared mental model across frontend, backend, data, and ops

- [intern_handbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/intern_handbook.md)
  - best starting point for interns
  - explains the business purpose, workflows, roles, and high-risk areas

- [project_documentation.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/project_documentation.md)
  - high-level project reference
  - acts as the broad project map

- [glossary.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/glossary.md)
  - defines important terms used across the app

## Technical Understanding

- [technical_architecture.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/technical_architecture.md)
  - system topology, runtime boundaries, data flow, failure points

- [frontend_architecture.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/frontend_architecture.md)
  - route structure, main views, polling and browser-state model

- [backend_architecture.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/backend_architecture.md)
  - backend module boundaries and responsibilities

- [collector_deep_dive.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/collector_deep_dive.md)
  - Playwright collector behavior, parsing helpers, fragility points

## Data And API Reference

- [database_schema_reference.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/database_schema_reference.md)
  - table-by-table explanation
  - relationships and truth hierarchy

- [postgres_primary_cutover_plan.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/postgres_primary_cutover_plan.md)
  - staged plan for moving production writes from SQLite to PostgreSQL
  - maps current write paths, dual-write strategy, and SQLite retirement

- [api_reference.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/api_reference.md)
  - endpoint families, critical flows, and change-risk notes

- [inventory_data_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/inventory_data_guide.md)
  - product field meanings and safe data-handling rules

## Live Operations

- [runbook_live_operations.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/runbook_live_operations.md)
  - before-live, during-live, and after-live checklist

- [main_runtime_complete.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/main_runtime_complete.md)
  - main runtime completion milestone, deferred bridge tracks, and stabilization checklist

- [runtime_stabilization_runbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/runtime_stabilization_runbook.md)
  - exact commands and pass/fail checks for FastAPI, Redis, Celery, bridge hits, and latency review

- [deployment_service_autostart.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/deployment_service_autostart.md)
  - service autostart setup, RBAC policy workflow, and frontend diagnostics inspection

- [whatnot_runtime_burn_in_checklist.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/whatnot_runtime_burn_in_checklist.md)
  - Checklist for validating Postgres-only Whatnot runtime before SQLite retirement

- [perfume_stream_playbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/perfume_stream_playbook.md)
  - stream-specific operating notes and workflow guidance

- [troubleshooting_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/troubleshooting_guide.md)
  - symptom -> likely cause -> where to check -> safe next action

- [recovery_playbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/recovery_playbook.md)
  - duplicate cleanup, restore flows, cancellation cleanup, restart recovery

## Migration / Cutover

- [main_runtime_complete.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/main_runtime_complete.md)
  - main runtime completion milestone and deferred legacy tracks

- [migration_progress_tracker.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/migration_progress_tracker.md)
  - current migration status, completed work, deferred tracks, and resume order

- [runtime_stabilization_runbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/runtime_stabilization_runbook.md)
  - day-to-day stabilization runbook for the completed main runtime

- [whatnot_runtime_burn_in_checklist.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/whatnot_runtime_burn_in_checklist.md)
  - Checklist for validating Postgres-only Whatnot runtime before SQLite retirement

## Engineering Process

- [contribution_safety_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/contribution_safety_guide.md)
  - what is safe to change and what is risky

- [testing_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/testing_guide.md)
  - what to test for UI, inventory, and winner-flow changes

- [gitlab_onboarding_from_odoo.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/gitlab_onboarding_from_odoo.md)
  - GitLab onboarding notes tied to Odoo users

- [odoo_users_export_2026-04-05.csv](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/odoo_users_export_2026-04-05.csv)
  - exported Odoo users used for onboarding/reference

## Suggested Reading Paths

### For interns
1. [intern_handbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/intern_handbook.md)
2. [glossary.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/glossary.md)
3. [contribution_safety_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/contribution_safety_guide.md)
4. [testing_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/testing_guide.md)

### For backend contributors
1. [technical_architecture.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/technical_architecture.md)
2. [backend_architecture.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/backend_architecture.md)
3. [database_schema_reference.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/database_schema_reference.md)
4. [api_reference.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/api_reference.md)

### For frontend contributors
1. [intern_handbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/intern_handbook.md)
2. [frontend_architecture.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/frontend_architecture.md)
3. [contribution_safety_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/contribution_safety_guide.md)
4. [testing_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/testing_guide.md)

### For operations / admin
1. [runbook_live_operations.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/runbook_live_operations.md)
2. [troubleshooting_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/troubleshooting_guide.md)
3. [recovery_playbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/recovery_playbook.md)
4. [inventory_data_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/inventory_data_guide.md)
