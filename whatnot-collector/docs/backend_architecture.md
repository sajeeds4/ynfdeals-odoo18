# Backend Architecture

## Purpose
This document explains how the backend is organized.

Main backend path:
- [server](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/server)

## Main Modules

### `api.py`
Central API layer.

Responsibilities:
- route handling
- stream control
- inventory APIs
- winner assignment APIs
- diagnostics APIs
- auth endpoints

### `company_db.py`
Business database helpers and schema owner.

Responsibilities:
- schema creation
- product CRUD
- session and lot persistence
- winner assignment persistence
- auction results
- sale orders

### `events_db.py`
Raw event query and interpretation layer.

Responsibilities:
- query raw events
- reconstruct sold lots
- normalize usernames and price extraction
- audience and seller insight helpers

### `collector_manager.py`
Collector process orchestration.

Responsibilities:
- start/stop live collector
- manage spectator worker state
- persist collector process state

### `auth.py`
Dashboard authentication/session layer.

### `state.py`
JSON-based runtime state files.

### `config.py`
Configuration loading and path resolution.

## Service Boundary Rule
If the issue is about:

- route handling or endpoint output -> `api.py`
- business truth and persistence -> `company_db.py`
- raw collector interpretation -> `events_db.py`
- process lifecycle -> `collector_manager.py`
- auth/session -> `auth.py`
- state JSON files -> `state.py`
