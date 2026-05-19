# Collector Deep Dive

## Purpose
This document explains the collector internals and fragility points.

Main file:
- [src/collector/main.py](/home/cybertechna/AethrixSystems_Portable/hjay9672-WN%20/whatnot-collector/src/collector/main.py)

## Core Responsibilities
- load cookies
- launch Playwright
- open Whatnot live pages
- parse visible stream UI
- insert raw events into SQLite

## Key Parsing Areas

### Lot number extraction
Helpers:
- `_extract_lot_number_from_text`

### Winner extraction
Helpers:
- `_normalize_winner_text`
- `_extract_banner_winner_username`
- `_looks_like_username`

### Price extraction
Helpers:
- `_extract_sold_price`
- `_extract_live_bid_price`
- `_parse_price_token`

## Event Types Emitted
Common output:
- lot updates
- auction winners
- chat messages
- bid updates
- viewer counts

## Fragility Points

### DOM changes
If Whatnot changes classes or structure, extraction can silently degrade.

### Timing changes
Some winner information exists only briefly.

### Cloudflare / anti-bot friction
Certain streams may be blocked before collection even begins.

### Page navigation mid-tick
If the page navigates while the collector is reading it, an event cycle can fail.

## Contributor Advice
- treat selector changes as high risk
- test against real or recent live data when possible
- do not assume one stream’s DOM behavior represents all streams
