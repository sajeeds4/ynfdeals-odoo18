import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchApi, postApi } from '../hooks/useApi';

const fmt = (n) => (n == null ? '--' : `$${Number(n).toFixed(2)}`);

export default function InternalPos() {
  const [params] = useSearchParams();
  const token = params.get('token') || '';
  const guestMode = !token;
  const [employee, setEmployee] = useState(null);
  const [products, setProducts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [buyerProfiles, setBuyerProfiles] = useState([]);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [buyerName, setBuyerName] = useState('');
  const [buyerType, setBuyerType] = useState('walk_in');
  const [buyerPhone, setBuyerPhone] = useState('');
  const [buyerEmail, setBuyerEmail] = useState('');
  const [search, setSearch] = useState('');
  const [notes, setNotes] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [cart, setCart] = useState([]);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [scanOpen, setScanOpen] = useState(false);
  const [splitLineIds, setSplitLineIds] = useState([]);
  const [splitQtyMap, setSplitQtyMap] = useState({});
  const [mergeTargetId, setMergeTargetId] = useState('');
  const [viewportWidth, setViewportWidth] = useState(
    typeof window === 'undefined' ? 1280 : window.innerWidth,
  );

  const isTabletOrSmaller = viewportWidth < 1080;
  const isMobile = viewportWidth < 720;
  const isTinyMobile = viewportWidth < 480;
  const compactHistory = isMobile;

  function toCartRow(line) {
    return {
      row_key: line.id ? `line-${line.id}` : `product-${line.product_id}`,
      line_id: line.id || null,
      product_id: line.product_id,
      description: line.description || line.product_name,
      barcode: line.barcode,
      sku: line.sku,
      qty: Number(line.qty || 0),
      unit_price: Number(line.unit_price || 0),
      on_hand_qty: Number(line.on_hand_qty || 0),
    };
  }

  async function loadProducts(nextSearch = '') {
    const query = String(nextSearch || '').trim();
    const params = new URLSearchParams();
    if (token) params.set('token', token);
    if (query) params.set('q', query);
    const data = await fetchApi(`/api/internal_pos/products?${params.toString()}`);
    setProducts(data.rows || []);
  }

  async function loadBuyerProfiles(query = '') {
    const params = new URLSearchParams();
    if (query) params.set('q', query);
    const data = await fetchApi(`/api/internal_pos/buyers?${params.toString()}`);
    setBuyerProfiles(data.rows || []);
  }

  async function loadHistory(profile = {}) {
    const params = new URLSearchParams();
    if (profile?.employee_id) params.set('employee_id', profile.employee_id);
    else if (profile?.buyer_name || buyerName) params.set('buyer_name', profile?.buyer_name || buyerName);
    if (profile?.buyer_phone || buyerPhone) params.set('buyer_phone', profile?.buyer_phone || buyerPhone);
    if (profile?.buyer_email || buyerEmail) params.set('buyer_email', profile?.buyer_email || buyerEmail);
    if (!params.toString()) {
      setOrders([]);
      return;
    }
    const data = await fetchApi(`/api/internal_pos/orders/history?${params.toString()}`);
    setOrders(data.rows || []);
  }

  async function loadOrderDetail(orderId) {
    if (!guestMode || !orderId || !buyerName.trim()) return;
    const params = new URLSearchParams({
      id: String(orderId),
      buyer_name: buyerName.trim(),
    });
    if (buyerPhone.trim()) params.set('buyer_phone', buyerPhone.trim());
    if (buyerEmail.trim()) params.set('buyer_email', buyerEmail.trim());
    const data = await fetchApi(`/api/internal_pos/orders/detail?${params.toString()}`);
    const order = data.order || null;
    setSelectedOrder(order);
    setNotes(order?.notes || '');
    setPaymentMethod(order?.payment_method || 'cash');
    setBuyerType(order?.buyer_type || 'walk_in');
    if (order?.buyer_phone) setBuyerPhone(order.buyer_phone);
    if (order?.buyer_email) setBuyerEmail(order.buyer_email);
    setCart((order?.lines || []).map((line) => toCartRow(line)));
    setSplitLineIds([]);
    setSplitQtyMap({});
    setMergeTargetId('');
    setMessage(`Loaded invoice #${order?.id}.`);
  }

  async function load() {
    setLoading(true);
    try {
      const meUrl = token ? `/api/internal_pos/me?token=${encodeURIComponent(token)}` : '/api/internal_pos/me';
      const [meData, orderData, buyerData] = await Promise.all([
        fetchApi(meUrl),
        token ? fetchApi(`/api/internal_pos/orders/mine?token=${encodeURIComponent(token)}`) : Promise.resolve({ rows: [] }),
        loadBuyerProfiles(''),
      ]);
      setEmployee(meData.employee || null);
      setOrders(orderData.rows || []);
      await loadProducts(search);
    } catch (error) {
      setMessage(error.message || 'Could not load internal POS.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [token]);

  useEffect(() => {
    const timer = setTimeout(() => {
      loadProducts(search).catch(() => {});
      if (guestMode) loadBuyerProfiles(buyerName).catch(() => {});
    }, 180);
    return () => clearTimeout(timer);
  }, [search, token, guestMode, buyerName]);

  useEffect(() => {
    function handleResize() {
      setViewportWidth(window.innerWidth);
    }
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const cartTotal = useMemo(() => (
    cart.reduce((sum, item) => sum + (Number(item.qty || 0) * Number(item.unit_price || 0)), 0)
  ), [cart]);

  function addToCart(product) {
    setCart((current) => {
      const found = current.find((item) => String(item.product_id) === String(product.id) && !item.line_id);
      if (found) {
        return current.map((item) => (
          String(item.product_id) === String(product.id) && !item.line_id
            ? { ...item, qty: Number(item.qty || 0) + 1 }
            : item
        ));
      }
      return [
        ...current,
        {
          row_key: `product-${product.id}`,
          line_id: null,
          product_id: product.id,
          description: product.name,
          barcode: product.barcode,
          sku: product.sku,
          qty: 1,
          unit_price: Number(product.cost_price || 0),
          on_hand_qty: Number(product.on_hand_qty || 0),
        },
      ];
    });
  }

  function updateCart(rowKey, key, value) {
    setCart((current) => current.map((item) => {
      if (String(item.row_key) !== String(rowKey)) return item;
      return { ...item, [key]: key === 'qty' || key === 'unit_price' ? Number(value || 0) : value };
    }).filter((item) => Number(item.qty || 0) > 0));
  }

  function resetDraftState() {
    setSelectedOrder(null);
    setSplitLineIds([]);
    setSplitQtyMap({});
    setMergeTargetId('');
    setCart([]);
    setNotes('');
    setPaymentMethod('cash');
  }

  async function lookupCode(code) {
    const clean = String(code || '').trim();
    if (!clean) return;
    try {
      const params = new URLSearchParams({ token, code: clean });
      const data = await fetchApi(`/api/internal_pos/products?${params.toString()}`);
      const first = (data.rows || [])[0];
      if (first) {
        addToCart(first);
        setMessage(`Added ${first.name} to cart.`);
      } else {
        setMessage(`No product matched ${clean}.`);
      }
    } catch (error) {
      setMessage(error.message || 'Could not scan barcode.');
    }
  }

  async function submitOrder() {
    if (!cart.length) return;
    setSubmitting(true);
    setMessage('');
    try {
      const payload = {
        token,
        employee_name: guestMode ? buyerName : undefined,
        employee_id: guestMode ? undefined : employee?.employee_id,
        payment_method: paymentMethod,
        notes,
        buyer_type: guestMode ? buyerType : 'employee',
        buyer_phone: guestMode ? buyerPhone : '',
        buyer_email: guestMode ? buyerEmail : '',
        lines: cart.map((item) => ({
          id: item.line_id || 0,
          product_id: item.product_id,
          barcode: item.barcode,
          sku: item.sku,
          qty: Number(item.qty || 0),
          unit_price: Number(item.unit_price || 0),
        })),
      };
      if (guestMode && selectedOrder?.id) {
        await postApi('/api/internal_pos/orders/update', {
          id: selectedOrder.id,
          buyer_name: buyerName,
          buyer_phone: buyerPhone,
          buyer_email: buyerEmail,
          ...payload,
        });
      } else {
        await postApi('/api/internal_pos/orders', payload);
      }
      resetDraftState();
      setMessage(guestMode ? (selectedOrder?.id ? 'Draft invoice updated.' : 'Invoice submitted.') : 'Order submitted for approval.');
      if (guestMode) await loadHistory({ buyer_name: buyerName });
      await load();
    } catch (error) {
      setMessage(error.message || 'Could not submit order.');
    } finally {
      setSubmitting(false);
    }
  }

  async function splitDraftOrder() {
    if (!selectedOrder?.id || !splitLineIds.length) return;
    setSubmitting(true);
    setMessage('');
    try {
      const result = await postApi('/api/internal_pos/orders/split', {
        id: selectedOrder.id,
        buyer_name: buyerName,
        buyer_phone: buyerPhone,
        buyer_email: buyerEmail,
        line_ids: splitLineIds,
        line_items: splitLineIds.map((id) => ({
          id,
          qty: Number(splitQtyMap[String(id)] || cart.find((item) => Number(item.line_id) === Number(id))?.qty || 0),
        })),
      });
      const nextOrder = result?.source_order || null;
      setSelectedOrder(nextOrder);
      setCart((nextOrder?.lines || []).map((line) => toCartRow(line)));
      setSplitLineIds([]);
      setSplitQtyMap({});
      setMessage(result?.split_order?.id ? `Split into invoice #${result.split_order.id}.` : 'Invoice split.');
      await loadHistory({ buyer_name: buyerName });
    } catch (error) {
      setMessage(error.message || 'Could not split draft invoice.');
    } finally {
      setSubmitting(false);
    }
  }

  async function mergeDraftOrder() {
    if (!selectedOrder?.id || !mergeTargetId) return;
    setSubmitting(true);
    setMessage('');
    try {
      const result = await postApi('/api/internal_pos/orders/merge', {
        source_id: selectedOrder.id,
        target_id: Number(mergeTargetId),
        buyer_name: buyerName,
        buyer_phone: buyerPhone,
        buyer_email: buyerEmail,
      });
      const nextOrder = result?.target_order || null;
      setSelectedOrder(nextOrder);
      setCart((nextOrder?.lines || []).map((line) => toCartRow(line)));
      setMergeTargetId('');
      setMessage(nextOrder?.id ? `Merged into invoice #${nextOrder.id}.` : 'Invoices merged.');
      await loadHistory({ buyer_name: buyerName });
    } catch (error) {
      setMessage(error.message || 'Could not merge draft invoice.');
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <div style={loadingShell}>Loading internal POS…</div>;
  }

  return (
    <div style={shellStyle}>
      <div style={heroStyle}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 900, letterSpacing: '0.09em', textTransform: 'uppercase', color: 'rgba(15,23,42,0.64)' }}>{guestMode ? 'Guest Self Checkout' : 'In-House Mobile POS'}</div>
          <h1 style={{ margin: '6px 0 0', fontSize: isTinyMobile ? 22 : 28, lineHeight: 1.05, letterSpacing: '-0.04em' }}>
            {guestMode ? (buyerName || 'Scan First, Then Choose Your Name') : (employee?.employee_name || 'Employee POS')}
          </h1>
          <div style={{ marginTop: 8, fontSize: 14, color: 'rgba(15,23,42,0.68)' }}>
            {guestMode
              ? 'Scan products, choose your name from prior purchases or type a new one, review history, and build your invoice without logging in.'
              : 'Scan or search products, build your cart, and submit for manager approval.'}
          </div>
        </div>
        <div style={{ display: 'grid', gap: 8, justifyItems: isMobile ? 'start' : 'end', width: isMobile ? '100%' : 'auto' }}>
          <div style={metricPillStyle}>{guestMode ? `Past invoices: ${orders.length}` : `Pending orders: ${orders.filter((row) => row.status === 'pending_approval').length}`}</div>
          <div style={metricPillStyle}>{guestMode ? `Saved buyers: ${buyerProfiles.length}` : `Approved: ${orders.filter((row) => row.status === 'approved').length}`}</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: isTabletOrSmaller ? 'minmax(0, 1fr)' : 'minmax(0, 1fr) 360px', gap: 18, alignItems: 'start' }}>
        <div style={{ display: 'grid', gap: 16 }}>
          {guestMode ? (
            <section style={panelStyle}>
              <div style={{ display: 'grid', gap: 10 }}>
                <div style={{ fontSize: 12, fontWeight: 900, color: 'rgba(15,23,42,0.55)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Buyer</div>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1.4fr 1fr 1fr', gap: 10 }}>
                  <input value={buyerName} onChange={(event) => setBuyerName(event.target.value)} placeholder="Enter your name or pick from history" style={searchStyle} list="self-checkout-buyers" />
                  <input value={buyerPhone} onChange={(event) => setBuyerPhone(event.target.value)} placeholder="Phone (optional)" style={searchStyle} />
                  <input value={buyerEmail} onChange={(event) => setBuyerEmail(event.target.value)} placeholder="Email (optional)" style={searchStyle} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '220px auto auto', gap: 10, alignItems: 'center' }}>
                  <select value={buyerType} onChange={(event) => setBuyerType(event.target.value)} style={searchStyle}>
                    <option value="walk_in">Walk-in</option>
                    <option value="friends_family">Friends / Family</option>
                    <option value="wholesale">Wholesale</option>
                    <option value="sample">Sample / Comp</option>
                  </select>
                  <button type="button" onClick={() => loadHistory({ buyer_name: buyerName })} style={ghostButtonStyle}>Load Purchase History</button>
                  <button type="button" onClick={() => { setBuyerName(''); setBuyerPhone(''); setBuyerEmail(''); setOrders([]); resetDraftState(); }} style={ghostButtonStyle}>New Buyer</button>
                </div>
                <datalist id="self-checkout-buyers">
                  {buyerProfiles.map((profile) => (
                    <option key={profile.employee_id} value={profile.buyer_name}>{profile.buyer_type || 'walk_in'} · {profile.buyer_phone || profile.buyer_email || 'No contact'}</option>
                  ))}
                </datalist>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  {buyerProfiles.slice(0, 8).map((profile) => (
                    <button
                      key={`profile-${profile.employee_id}`}
                      type="button"
                      onClick={() => {
                        setBuyerName(profile.buyer_name || '');
                        setBuyerType(profile.buyer_type || 'walk_in');
                        setBuyerPhone(profile.buyer_phone || '');
                        setBuyerEmail(profile.buyer_email || '');
                        loadHistory(profile).catch(() => {});
                      }}
                      style={ghostButtonStyle}
                    >
                      {profile.buyer_name}
                    </button>
                  ))}
                </div>
              </div>
            </section>
          ) : null}
          <section style={panelStyle}>
            <div style={{ display: 'grid', gap: 10 }}>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={isMobile ? 'Scan or search barcode...' : 'Search products, barcode, SKU...'}
                style={isMobile ? mobileScanInputStyle : searchStyle}
              />
              <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 10 }}>
                <button type="button" onClick={() => setScanOpen((current) => !current)} style={isMobile ? mobilePrimaryButtonStyle : primaryButtonStyle}>{isMobile ? 'Open Camera Scanner' : 'Use Camera Scan'}</button>
                <button type="button" onClick={() => lookupCode(search)} style={isMobile ? mobileGhostButtonStyle : ghostButtonStyle}>Lookup Current Code</button>
              </div>
            </div>
            {scanOpen ? <BarcodeScanner onDetected={lookupCode} onClose={() => setScanOpen(false)} /> : null}
            {message ? <div style={{ fontSize: 13, color: message.toLowerCase().includes('could not') || message.toLowerCase().includes('no product') ? '#b91c1c' : '#047857' }}>{message}</div> : null}
          </section>

          <section style={{ ...panelStyle, gap: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 900, color: 'rgba(15,23,42,0.55)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Products</div>
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(auto-fill, minmax(${isMobile ? 160 : 220}px, 1fr))`, gap: 14 }}>
              {products.map((product) => (
                <article key={product.id} style={productCardStyle}>
                  <div style={{ display: 'grid', gap: 8 }}>
                    <div style={{ fontWeight: 800, fontSize: 15, lineHeight: 1.3 }}>{product.name}</div>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 12, color: 'rgba(15,23,42,0.65)' }}>
                      <span>{product.category_name || 'Uncategorized'}</span>
                      <span>{product.storage_bin || 'No bin'}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                      <div>
                        <div style={{ fontSize: 12, color: 'rgba(15,23,42,0.54)' }}>Employee price</div>
                        <div style={{ fontSize: 22, fontWeight: 900 }}>{fmt(product.cost_price)}</div>
                      </div>
                      <div style={{ textAlign: 'right', color: Number(product.on_hand_qty || 0) <= Number(product.low_stock_threshold || 3) ? '#b91c1c' : 'rgba(15,23,42,0.7)', fontWeight: 800 }}>
                        {Number(product.on_hand_qty || 0)} left
                      </div>
                    </div>
                  </div>
                  <button type="button" onClick={() => addToCart(product)} style={isMobile ? mobilePrimaryButtonStyle : primaryButtonStyle}>Add to cart</button>
                </article>
              ))}
            </div>
          </section>
        </div>

        <aside style={{ display: 'grid', gap: 16, position: isTabletOrSmaller ? 'static' : 'sticky', top: 14, order: isTabletOrSmaller ? -1 : 0, paddingBottom: isMobile ? 110 : 0 }}>
          <section style={cartStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'rgba(15,23,42,0.52)' }}>
                  {selectedOrder?.id ? `Editing Invoice #${selectedOrder.id}` : 'Cart'}
                </div>
                <div style={{ fontSize: 20, fontWeight: 900 }}>{cart.length} items</div>
              </div>
              <div style={{ display: 'grid', justifyItems: 'end', gap: 6 }}>
                <div style={{ fontSize: 26, fontWeight: 900 }}>{fmt(cartTotal)}</div>
                {selectedOrder?.id ? (
                  <button type="button" onClick={resetDraftState} style={{ ...linkButtonStyle, color: '#f8fafc' }}>Leave draft</button>
                ) : null}
              </div>
            </div>
            <div style={{ display: 'grid', gap: 12, maxHeight: 380, overflowY: 'auto' }}>
              {cart.length ? cart.map((item) => (
                <div key={item.row_key} style={{ border: '1px solid rgba(148,163,184,0.18)', borderRadius: 18, padding: 12, background: 'rgba(255,255,255,0.84)', display: 'grid', gap: 10 }}>
                  <div style={{ fontWeight: 800 }}>{item.description}</div>
                  <div style={{ display: 'grid', gridTemplateColumns: isTinyMobile ? '1fr' : '1fr 1fr', gap: 10 }}>
                    <label style={fieldLabelStyle}>
                      Qty
                      <input type="number" min="1" step="1" value={item.qty} onChange={(event) => updateCart(item.row_key, 'qty', event.target.value)} style={fieldInputStyle} />
                    </label>
                    <label style={fieldLabelStyle}>
                      Price
                      <input type="number" step="0.01" value={item.unit_price} onChange={(event) => updateCart(item.row_key, 'unit_price', event.target.value)} style={fieldInputStyle} />
                    </label>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', fontSize: 12, flexWrap: 'wrap' }}>
                    <span style={{ color: Number(item.on_hand_qty || 0) <= 3 ? '#b91c1c' : 'rgba(15,23,42,0.64)', fontWeight: 700 }}>{item.on_hand_qty} left</span>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                      {selectedOrder?.id && item.line_id ? (
                        <>
                          <label style={{ display: 'flex', gap: 6, alignItems: 'center', color: '#0f172a', fontWeight: 700 }}>
                            <input
                              type="checkbox"
                              checked={splitLineIds.includes(item.line_id)}
                              onChange={(event) => {
                                setSplitLineIds((current) => (
                                  event.target.checked
                                    ? [...new Set([...current, item.line_id])]
                                    : current.filter((id) => Number(id) !== Number(item.line_id))
                                ));
                              }}
                            />
                            Split
                          </label>
                          {splitLineIds.includes(item.line_id) ? (
                            <input
                              type="number"
                              min="1"
                              step="1"
                              value={splitQtyMap[String(item.line_id)] || item.qty}
                              onChange={(event) => setSplitQtyMap((current) => ({ ...current, [String(item.line_id)]: event.target.value }))}
                              style={{ ...fieldInputStyle, width: 84, padding: '8px 10px' }}
                            />
                          ) : null}
                        </>
                      ) : null}
                      <button type="button" onClick={() => updateCart(item.row_key, 'qty', 0)} style={linkButtonStyle}>Remove</button>
                    </div>
                  </div>
                </div>
              )) : <div style={{ fontSize: 13, color: 'rgba(15,23,42,0.58)' }}>Your cart is empty.</div>}
            </div>
            {selectedOrder?.id ? (
              <div style={{ display: 'grid', gap: 10 }}>
                <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr auto', gap: 10, alignItems: 'end' }}>
                  <label style={fieldLabelStyle}>
                    Merge into invoice
                    <select value={mergeTargetId} onChange={(event) => setMergeTargetId(event.target.value)} style={fieldInputStyle}>
                      <option value="">Choose a draft invoice</option>
                      {orders
                        .filter((order) => Number(order.id) !== Number(selectedOrder.id) && ['draft', 'pending_approval'].includes(String(order.status || '')))
                        .map((order) => (
                          <option key={`merge-${order.id}`} value={order.id}>
                            #{order.id} · {fmt(order.total_amount)} · {order.line_count} lines
                          </option>
                        ))}
                    </select>
                  </label>
                  <button type="button" onClick={mergeDraftOrder} disabled={submitting || !mergeTargetId} style={isMobile ? mobileGhostButtonStyle : ghostButtonStyle}>Merge Draft</button>
                </div>
                <button type="button" onClick={splitDraftOrder} disabled={submitting || !splitLineIds.length} style={isMobile ? mobileGhostButtonStyle : ghostButtonStyle}>Split Selected Lines</button>
              </div>
            ) : null}
            <label style={fieldLabelStyle}>
              Payment method
              <select value={paymentMethod} onChange={(event) => setPaymentMethod(event.target.value)} style={fieldInputStyle}>
                {!guestMode ? <option value="payroll">Payroll deduction</option> : null}
                <option value="cash">Cash</option>
                <option value="card">Card</option>
                <option value="zelle">Zelle</option>
                <option value="venmo">Venmo</option>
                <option value="internal_credit">Internal credit</option>
                <option value="free">Free / sample</option>
              </select>
            </label>
            <label style={fieldLabelStyle}>
              Notes
              <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} style={{ ...fieldInputStyle, resize: 'vertical', minHeight: 88 }} placeholder="Optional note for manager" />
            </label>
            <button type="button" onClick={submitOrder} disabled={submitting || !cart.length || (guestMode && !buyerName.trim())} style={isMobile ? mobilePrimaryButtonStyle : primaryButtonStyle}>
              {submitting ? 'Submitting...' : guestMode ? (selectedOrder?.id ? 'Save Invoice Changes' : 'Create Invoice') : 'Submit Order for Approval'}
            </button>
          </section>

          <section style={panelStyle}>
            <div style={{ fontSize: 12, fontWeight: 900, color: 'rgba(15,23,42,0.55)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{guestMode ? 'Purchase History' : 'My Orders'}</div>
            <div style={{ display: 'grid', gap: 10 }}>
              {orders.length ? orders.map((order) => (
                <div key={order.id} style={{ border: '1px solid rgba(148,163,184,0.18)', borderRadius: 16, padding: 12, background: 'rgba(255,255,255,0.82)', display: 'grid', gap: 6 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                    <div style={{ fontWeight: 800 }}>Order #{order.id}</div>
                    <span style={statusBadgeStyle(order.status)}>{String(order.status || '').replace(/_/g, ' ')}</span>
                  </div>
                  <div style={{ fontSize: 12, color: 'rgba(15,23,42,0.64)' }}>{order.line_count} lines · {order.units_requested} units · {fmt(order.total_amount)}</div>
                  <div style={{ fontSize: 12, color: 'rgba(15,23,42,0.52)' }}>
                    {order.created_at ? new Date(order.created_at).toLocaleString() : 'Date unavailable'}
                  </div>
                  {guestMode && ['draft', 'pending_approval'].includes(String(order.status || '')) ? (
                    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                      <button type="button" onClick={() => loadOrderDetail(order.id)} style={isMobile ? mobileGhostButtonStyle : ghostButtonStyle}>Resume Draft</button>
                    </div>
                  ) : null}
                </div>
              )) : <div style={{ fontSize: 13, color: 'rgba(15,23,42,0.58)' }}>No submitted orders yet.</div>}
            </div>
          </section>
        </aside>
      </div>
      {isMobile ? (
        <div style={mobileCheckoutBarStyle}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'rgba(15,23,42,0.56)' }}>
              {selectedOrder?.id ? `Invoice #${selectedOrder.id}` : 'Checkout'}
            </div>
            <div style={{ fontSize: 22, fontWeight: 900, lineHeight: 1 }}>{fmt(cartTotal)}</div>
            <div style={{ fontSize: 12, color: 'rgba(15,23,42,0.62)' }}>{cart.length} items{guestMode && buyerName ? ` · ${buyerName}` : ''}</div>
          </div>
          <button
            type="button"
            onClick={submitOrder}
            disabled={submitting || !cart.length || (guestMode && !buyerName.trim())}
            style={{ ...mobilePrimaryButtonStyle, margin: 0, minWidth: 150 }}
          >
            {submitting ? 'Submitting...' : selectedOrder?.id ? 'Save' : 'Checkout'}
          </button>
        </div>
      ) : null}
    </div>
  );
}

function BarcodeScanner({ onDetected, onClose }) {
  const videoRef = useRef(null);
  const detectorRef = useRef(null);
  const streamRef = useRef(null);
  const rafRef = useRef(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    async function start() {
      try {
        if (!('BarcodeDetector' in window)) {
          setError('This phone browser does not support live barcode detection yet. Use manual barcode lookup instead.');
          return;
        }
        detectorRef.current = new window.BarcodeDetector({ formats: ['ean_13', 'upc_a', 'upc_e', 'code_128', 'qr_code'] });
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } },
          audio: false,
        });
        if (!active) return;
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        scan();
      } catch (scanError) {
        setError(scanError.message || 'Could not open camera.');
      }
    }

    async function scan() {
      if (!active || !videoRef.current || !detectorRef.current) return;
      try {
        const codes = await detectorRef.current.detect(videoRef.current);
        if (codes?.length) {
          const value = codes[0]?.rawValue;
          if (value) {
            onDetected(value);
            onClose();
            return;
          }
        }
      } catch {
        // keep scanning
      }
      rafRef.current = window.requestAnimationFrame(scan);
    }

    start();
    return () => {
      active = false;
      if (rafRef.current) window.cancelAnimationFrame(rafRef.current);
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
    };
  }, [onDetected, onClose]);

  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <div style={{ position: 'relative', borderRadius: 22, overflow: 'hidden', background: '#0f172a' }}>
        <video ref={videoRef} muted playsInline style={{ width: '100%', display: error ? 'none' : 'block', minHeight: 220, objectFit: 'cover' }} />
        {error ? <div style={{ padding: 18, color: 'white', fontSize: 13 }}>{error}</div> : null}
      </div>
      <button type="button" onClick={onClose} style={ghostButtonStyle}>Close scanner</button>
    </div>
  );
}

const shellStyle = {
  minHeight: '100vh',
  background: 'radial-gradient(circle at top left, rgba(14,165,233,0.18), transparent 28%), radial-gradient(circle at top right, rgba(249,115,22,0.16), transparent 24%), linear-gradient(180deg, #f8fafc 0%, #fffaf0 100%)',
  padding: '18px 14px 28px',
  display: 'grid',
  gap: 18,
};

const heroStyle = {
  borderRadius: 28,
  background: 'linear-gradient(135deg, rgba(255,255,255,0.98), rgba(255,247,237,0.96))',
  border: '1px solid rgba(148,163,184,0.18)',
  boxShadow: '0 18px 44px rgba(15,23,42,0.08)',
  padding: '18px 20px',
  display: 'flex',
  justifyContent: 'space-between',
  gap: 12,
  flexWrap: 'wrap',
  alignItems: 'center',
};

const panelStyle = {
  borderRadius: 26,
  background: 'rgba(255,255,255,0.88)',
  border: '1px solid rgba(148,163,184,0.18)',
  boxShadow: '0 16px 34px rgba(15,23,42,0.06)',
  padding: 16,
  display: 'grid',
  gap: 14,
};

const cartStyle = {
  ...panelStyle,
  background: 'linear-gradient(180deg, rgba(30,41,59,0.96), rgba(15,23,42,0.98))',
  color: 'white',
};

const metricPillStyle = {
  borderRadius: 999,
  padding: '8px 12px',
  background: 'rgba(255,255,255,0.78)',
  border: '1px solid rgba(148,163,184,0.16)',
  fontSize: 12,
  fontWeight: 800,
};

const searchStyle = {
  width: '100%',
  border: '1px solid rgba(148,163,184,0.22)',
  borderRadius: 18,
  padding: '14px 16px',
  fontSize: 16,
  background: 'white',
};

const mobileScanInputStyle = {
  ...searchStyle,
  padding: '18px 18px',
  fontSize: 18,
  fontWeight: 700,
  borderRadius: 20,
};

const productCardStyle = {
  borderRadius: 22,
  border: '1px solid rgba(148,163,184,0.18)',
  background: 'linear-gradient(180deg, rgba(255,255,255,0.96), rgba(248,250,252,0.95))',
  padding: 14,
  display: 'grid',
  gap: 14,
};

const primaryButtonStyle = {
  width: '100%',
  border: 'none',
  borderRadius: 18,
  background: 'linear-gradient(135deg, #2563eb, #7c3aed)',
  color: 'white',
  fontWeight: 900,
  padding: '13px 16px',
  fontSize: 15,
  cursor: 'pointer',
};

const mobilePrimaryButtonStyle = {
  ...primaryButtonStyle,
  padding: '16px 18px',
  fontSize: 16,
  borderRadius: 20,
};

const ghostButtonStyle = {
  width: '100%',
  borderRadius: 18,
  background: 'rgba(255,255,255,0.88)',
  color: '#1f2937',
  fontWeight: 800,
  padding: '12px 16px',
  fontSize: 14,
  border: '1px solid rgba(148,163,184,0.24)',
  cursor: 'pointer',
};

const mobileGhostButtonStyle = {
  ...ghostButtonStyle,
  padding: '15px 16px',
  fontSize: 15,
  borderRadius: 20,
};

const fieldLabelStyle = {
  display: 'grid',
  gap: 6,
  fontSize: 12,
  fontWeight: 800,
  color: 'inherit',
};

const fieldInputStyle = {
  width: '100%',
  borderRadius: 14,
  border: '1px solid rgba(148,163,184,0.24)',
  padding: '11px 12px',
  fontSize: 14,
  background: 'rgba(255,255,255,0.94)',
  color: '#0f172a',
};

const linkButtonStyle = {
  border: 'none',
  background: 'transparent',
  color: '#2563eb',
  fontWeight: 800,
  cursor: 'pointer',
  padding: 0,
};

const loadingShell = {
  minHeight: '100vh',
  display: 'grid',
  placeItems: 'center',
  background: 'linear-gradient(180deg, #f8fafc 0%, #fffaf0 100%)',
  color: '#0f172a',
  fontWeight: 800,
};

const mobileCheckoutBarStyle = {
  position: 'fixed',
  left: 12,
  right: 12,
  bottom: 12,
  zIndex: 40,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
  padding: '12px 14px',
  borderRadius: 22,
  background: 'rgba(255,255,255,0.96)',
  border: '1px solid rgba(148,163,184,0.18)',
  boxShadow: '0 20px 40px rgba(15,23,42,0.16)',
  backdropFilter: 'blur(10px)',
};

function statusBadgeStyle(status) {
  const tone = {
    pending_approval: ['rgba(245,158,11,0.14)', '#b45309'],
    approved: ['rgba(16,185,129,0.14)', '#047857'],
    rejected: ['rgba(239,68,68,0.14)', '#b91c1c'],
  }[status] || ['rgba(148,163,184,0.14)', '#475569'];
  return {
    display: 'inline-flex',
    alignItems: 'center',
    padding: '4px 10px',
    borderRadius: 999,
    background: tone[0],
    color: tone[1],
    fontSize: 11,
    fontWeight: 900,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
  };
}
