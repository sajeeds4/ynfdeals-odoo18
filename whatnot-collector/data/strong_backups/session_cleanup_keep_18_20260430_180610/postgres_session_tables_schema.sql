-- Lightweight PostgreSQL schema skeleton for local/dev bootstrap.
-- This is intentionally minimal and is not a full production backup.

CREATE SCHEMA IF NOT EXISTS sqlite_mirror;

CREATE TABLE IF NOT EXISTS sqlite_mirror.company_sessions (
  id BIGINT PRIMARY KEY,
  name TEXT,
  status TEXT,
  whatnot_account TEXT,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  total_revenue NUMERIC,
  total_profit NUMERIC,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sqlite_mirror.company_lots (
  id BIGINT PRIMARY KEY,
  session_id BIGINT,
  lot_number TEXT,
  status TEXT,
  winner_username TEXT,
  winning_price NUMERIC,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sqlite_mirror.auction_results (
  id BIGINT PRIMARY KEY,
  session_id BIGINT,
  lot_id BIGINT,
  lot_number TEXT,
  winner_username TEXT,
  sold_at TIMESTAMPTZ,
  sale_price NUMERIC,
  cost_price NUMERIC,
  profit NUMERIC,
  margin_pct NUMERIC,
  product_name TEXT,
  barcode TEXT,
  sku TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sqlite_mirror.buyer_groups (
  id BIGINT PRIMARY KEY,
  session_id BIGINT,
  buyer_username TEXT,
  display_name TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sqlite_mirror.sale_orders (
  id BIGINT PRIMARY KEY,
  session_id BIGINT,
  buyer_group_id BIGINT,
  whatnot_buyer_username TEXT,
  state TEXT,
  payment_status TEXT,
  total_amount NUMERIC,
  ordered_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sqlite_mirror.sale_order_lines (
  id BIGINT PRIMARY KEY,
  sale_order_id BIGINT,
  product_id BIGINT,
  description TEXT,
  qty NUMERIC,
  unit_price NUMERIC,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
