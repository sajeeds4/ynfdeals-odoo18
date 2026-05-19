# Frontend Architecture

## Purpose
This document explains the React frontend structure.

Main frontend root:
- [dashboard-vite](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite)

## Framework
- React
- Vite
- React Router

## Entry Point
- [src/App.jsx](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/App.jsx)

Responsibilities:
- top-level routing
- auth bootstrap
- theme toggle
- top nav visibility
- route protection

## Main Routes

- `/` -> TV Display
- `/operator` -> main operator page
- `/operator/tv-scanner` -> TV scanner station
- `/operator/winner-scanner` -> winner scanner station
- `/operator/obs` -> OBS operator panel
- `/session` -> session monitor
- `/company` -> back-office app area

Optional routes also exist for:
- spectator
- analytics
- competitors
- history
- dashboard
- users

## Main View Areas

### TV Display
Files:
- `LargeScreen.jsx`
- `TvScanner.jsx`

### Live Ops
Files:
- `Operator.jsx`
- `WinnerScanner.jsx`
- `OperatorObs.jsx`

### Back Office
Files:
- `Company.jsx`
- tab children in `src/views/company`

## State Model

### API polling
Main hook:
- [useApi.js](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/hooks/useApi.js)

Important behavior:
- polling-driven data refresh
- sessionStorage-backed API cache
- in-memory cache mirror

### Browser storage
Hook:
- [useBrowserState.js](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/dashboard-vite/src/hooks/useBrowserState.js)

Supports:
- `useLocalState`
- `useSessionState`

Used for:
- theme
- navigation visibility
- scanner preferences
- inventory filters/view state
- selected ticket state
- temporary tab working context

## Important Frontend Principle
The frontend is optimized for operational speed, but it is not the final source of truth for sales data.
