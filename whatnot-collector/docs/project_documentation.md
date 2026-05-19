# Whatnot Collector Project Documentation

## Overview
This project is a local-network livestream operations platform for Whatnot selling. It combines:

- live stream collection with Playwright
- a local API and business-logic layer
- a multi-device operations dashboard
- inventory management
- winner assignment workflows
- session and sale reporting
- diagnostics and recovery tools

It is built for real livestream operations, so the most important priorities are:

- speed
- operator clarity
- safe data flow
- recoverability when Whatnot data is noisy

## Best Starting Point
If you are new to the project, start here:

- [docs/INDEX.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/INDEX.md)
- [docs/intern_handbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/intern_handbook.md)
- [docs/technical_architecture.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/technical_architecture.md)
- [docs/api_reference.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/api_reference.md)
- [docs/contribution_safety_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/contribution_safety_guide.md)
- [docs/database_schema_reference.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/database_schema_reference.md)
- [docs/runbook_live_operations.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/runbook_live_operations.md)
- [docs/troubleshooting_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/troubleshooting_guide.md)
- [docs/frontend_architecture.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/frontend_architecture.md)
- [docs/backend_architecture.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/backend_architecture.md)
- [docs/collector_deep_dive.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/collector_deep_dive.md)
- [docs/inventory_data_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/inventory_data_guide.md)
- [docs/recovery_playbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/recovery_playbook.md)
- [docs/testing_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/testing_guide.md)
- [docs/glossary.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/glossary.md)

Those two files cover:

- business/workflow understanding
- technical/runtime understanding

## Main Components

### Collector
Path: `src/collector`

Responsibilities:
- open Whatnot pages
- collect raw lot, winner, bid, chat, and viewer events
- persist those raw events into local SQLite

Key files:
- [main.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/src/collector/main.py)
- [multitab.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/src/collector/multitab.py)
- [db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/src/collector/db.py)

### API Server
Path: `server`

Responsibilities:
- expose the dashboard API
- manage sessions, lots, winner tickets, auction results, sale orders, products, and diagnostics
- own the business logic that converts raw events into operational truth

Key files:
- [api.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/api.py)
- [company_db.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/company_db.py)
- [collector_manager.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/collector_manager.py)
- [auth.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/auth.py)
- [config.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server/config.py)

### Dashboard
Path: `dashboard-vite`

Responsibilities:
- TV display
- operator workflow
- winner scanner workflow
- inventory, sessions, sale orders, auction results
- diagnostics and settings

Key files:
- [App.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/App.jsx)
- [Company.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/Company.jsx)
- [Operator.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/Operator.jsx)
- [WinnerScanner.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/WinnerScanner.jsx)
- [TvScanner.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/TvScanner.jsx)
- [LargeScreen.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/LargeScreen.jsx)
- [Inventory.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/company/Inventory.jsx)
- [Diagnostics.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/views/company/Diagnostics.jsx)

## Data Stores

### Main operational database
- [whatnot.db](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/data/whatnot.db)

Contains:
- products
- company_sessions
- company_lots
- pending_winner_assignments
- auction_results
- sale_orders
- sale_order_lines
- pick list data

### Collector / runtime data
- [whatnot-collector/data](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/data)

Contains:
- runtime state files
- backups
- logs
- helper exports

### Odoo source data
Local Odoo source database:
- PostgreSQL database: `AethrixProd`

## Main Operational Rules

- trust `Winner Scanner confirmed` rows over provisional winner events
- do not trust Whatnot product titles for sold-product truth
- use barcode scans for actual sold product truth
- prefer backend fixes for integrity issues
- use diagnostics to investigate collector failures, duplicates, and data mismatches

## Local Network Performance Notes

- keep dashboard devices on the same LAN
- avoid restarting the API during live use unless necessary
- dedicate separate devices for:
  - TV display
  - Winner Scanner
  - main Operator
- use browser storage for fast page-state restoration

## Backups
Backups are frequently stored under:
- [whatnot-collector/data](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/data)

Common naming pattern:
- `whatnot.db.backup.*`

## Recommended Reading

- [README.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/README.md)
- [docs/intern_handbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/intern_handbook.md)
- [docs/technical_architecture.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/technical_architecture.md)
- [docs/api_reference.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/api_reference.md)
- [docs/contribution_safety_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/contribution_safety_guide.md)
- [docs/database_schema_reference.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/database_schema_reference.md)
- [docs/runbook_live_operations.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/runbook_live_operations.md)
- [docs/troubleshooting_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/troubleshooting_guide.md)
- [docs/frontend_architecture.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/frontend_architecture.md)
- [docs/backend_architecture.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/backend_architecture.md)
- [docs/collector_deep_dive.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/collector_deep_dive.md)
- [docs/inventory_data_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/inventory_data_guide.md)
- [docs/recovery_playbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/recovery_playbook.md)
- [docs/testing_guide.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/testing_guide.md)
- [docs/glossary.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/glossary.md)
- [docs/perfume_stream_playbook.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/perfume_stream_playbook.md)
- [docs/gitlab_onboarding_from_odoo.md](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/gitlab_onboarding_from_odoo.md)
- [docs/odoo_users_export_2026-04-05.csv](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/docs/odoo_users_export_2026-04-05.csv)
