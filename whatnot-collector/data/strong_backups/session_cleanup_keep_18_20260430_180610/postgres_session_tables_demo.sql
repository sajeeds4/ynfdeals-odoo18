-- Demo seed values for local/dev PostgreSQL bootstrap.
-- Safe, fake-looking records only.

INSERT INTO sqlite_mirror.company_sessions (
  id, name, status, whatnot_account, started_at, ended_at, total_revenue, total_profit, created_at, updated_at
)
VALUES
  (1001, 'Demo Session #1001', 'ended', 'ynfdeals', NOW() - INTERVAL '2 day', NOW() - INTERVAL '2 day' + INTERVAL '90 minute', 420.00, 155.00, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO sqlite_mirror.company_lots (
  id, session_id, lot_number, status, winner_username, winning_price, created_at, updated_at
)
VALUES
  (5001, 1001, 'L-001', 'sold', 'demo_buyer_01', 55.00, NOW(), NOW()),
  (5002, 1001, 'L-002', 'sold', 'demo_buyer_02', 38.00, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO sqlite_mirror.auction_results (
  id, session_id, lot_id, lot_number, winner_username, sold_at, sale_price, cost_price, profit, margin_pct, product_name, barcode, sku, created_at, updated_at
)
VALUES
  (9001, 1001, 5001, 'L-001', 'demo_buyer_01', NOW() - INTERVAL '2 day' + INTERVAL '20 minute', 55.00, 22.00, 33.00, 60.00, 'Demo Perfume A', 'DEMO-0001', 'SKU-DEMO-0001', NOW(), NOW()),
  (9002, 1001, 5002, 'L-002', 'demo_buyer_02', NOW() - INTERVAL '2 day' + INTERVAL '35 minute', 38.00, 15.00, 23.00, 60.53, 'Demo Perfume B', 'DEMO-0002', 'SKU-DEMO-0002', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO sqlite_mirror.buyer_groups (
  id, session_id, buyer_username, display_name, created_at, updated_at
)
VALUES
  (7001, 1001, 'demo_buyer_01', 'Demo Buyer One', NOW(), NOW()),
  (7002, 1001, 'demo_buyer_02', 'Demo Buyer Two', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO sqlite_mirror.sale_orders (
  id, session_id, buyer_group_id, whatnot_buyer_username, state, payment_status, total_amount, ordered_at, created_at, updated_at
)
VALUES
  (8001, 1001, 7001, 'demo_buyer_01', 'sale', 'paid', 55.00, NOW() - INTERVAL '2 day' + INTERVAL '25 minute', NOW(), NOW()),
  (8002, 1001, 7002, 'demo_buyer_02', 'sale', 'unpaid', 38.00, NOW() - INTERVAL '2 day' + INTERVAL '40 minute', NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

INSERT INTO sqlite_mirror.sale_order_lines (
  id, sale_order_id, product_id, description, qty, unit_price, created_at, updated_at
)
VALUES
  (8101, 8001, NULL, 'Demo Perfume A', 1, 55.00, NOW(), NOW()),
  (8102, 8002, NULL, 'Demo Perfume B', 1, 38.00, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;
