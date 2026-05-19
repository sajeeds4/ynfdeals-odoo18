import { useEffect, useMemo, useState } from 'react';
import { fetchApi, postApi } from '../../hooks/useApi';
import { KpiCard, SearchInput, PrimaryBtn, GhostBtn, TableShell, Thead, EmptyRow, fmtDt } from './utils';
import ynfLogo from '../../assets/ynf-logo.svg';

const fmt = (n) => (n == null ? '--' : `$${Number(n).toFixed(2)}`);
const fmtQty = (n) => (n == null ? '--' : Number(n).toLocaleString());
const productCost = (product) => Number(product?.standard_price ?? product?.cost_price ?? 0);
const productRetail = (product) => Number(product?.list_price ?? product?.retail_price ?? product?.standard_price ?? product?.cost_price ?? 0);

export default function InHouseSales() {
  const [data, setData] = useState({ rows: [], summary: {}, by_employee: [], employees: [] });
  const [products, setProducts] = useState([]);
  const [ordersData, setOrdersData] = useState({ rows: [], summary: {} });
  const [buyerProfiles, setBuyerProfiles] = useState([]);
  const [q, setQ] = useState('');
  const [posView, setPosView] = useState('tiles');
  const [selectedEmployeeFilter, setSelectedEmployeeFilter] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [receiptId, setReceiptId] = useState(null);
  const [receipt, setReceipt] = useState(null);
  const [receiptLoading, setReceiptLoading] = useState(false);
  const [editingReceipt, setEditingReceipt] = useState(false);
  const [receiptDraft, setReceiptDraft] = useState(null);
  const [receiptSaving, setReceiptSaving] = useState(false);
  const [splitLineIds, setSplitLineIds] = useState([]);
  const [splitQtyMap, setSplitQtyMap] = useState({});
  const [mergeTargetId, setMergeTargetId] = useState('');
  const [priceAdjustPercent, setPriceAdjustPercent] = useState('0');
  const [form, setForm] = useState({
    employee_id: '',
    employee_name: '',
    customer_phone: '',
    customer_email: '',
    customer_type: 'walk_in',
    payment_method: 'cash',
    price_mode: 'retail',
    product_id: '',
    product_query: '',
    barcode: '',
    qty: '1',
    unit_price: '',
    discount: '0',
    tax_rate: '0',
    notes: '',
  });
  const [cart, setCart] = useState([]);

  async function loadReceipt(orderId) {
    if (!orderId) return;
    setReceiptLoading(true);
    try {
      const result = await fetchApi(`/api/in_house_orders/detail?id=${orderId}`);
      const nextReceipt = result?.order || null;
      setReceipt(nextReceipt);
      setReceiptDraft(nextReceipt ? cloneReceiptDraft(nextReceipt) : null);
      setReceiptId(orderId);
      setEditingReceipt(false);
      setSplitLineIds([]);
      setSplitQtyMap({});
    } catch {
      setReceipt(null);
      setReceiptDraft(null);
    } finally {
      setReceiptLoading(false);
    }
  }

  function printReceipt(order = receipt) {
    if (!order) return;
    const lines = Array.isArray(order.lines) ? order.lines : [];
    const lineRows = lines.map((line) => `
      <tr>
        <td>${line.description || line.product_name || 'Item'}</td>
        <td>${Number(line.qty || 0).toLocaleString()}</td>
        <td>$${Number(line.unit_price || 0).toFixed(2)}</td>
        <td>$${Number(line.line_total || line.subtotal || 0).toFixed(2)}</td>
      </tr>
    `).join('');
    const popup = window.open('', '_blank', 'width=900,height=700');
    if (!popup) return;
    popup.document.write(`
      <!doctype html>
      <html>
      <head>
        <title>Receipt #${order.id}</title>
        <style>
          body { font-family: Arial, sans-serif; padding: 24px; color: #111827; }
          .invoice-header { display:flex; justify-content:space-between; align-items:flex-start; gap:18px; margin-bottom:18px; border-bottom:2px solid #e5e7eb; padding-bottom:16px; }
          .brand { display:flex; align-items:center; gap:12px; }
          .brand img { width:54px; height:54px; border-radius:12px; }
          .company { font-size:22px; font-weight:800; line-height:1.1; }
          .company-sub { margin-top:4px; color:#64748b; font-size:12px; line-height:1.45; }
          .invoice-title { text-align:right; }
          h1 { margin: 0 0 8px; font-size: 24px; }
          .meta { margin-bottom: 20px; color: #4b5563; font-size: 14px; }
          table { width: 100%; border-collapse: collapse; margin-top: 16px; }
          th, td { border-bottom: 1px solid #e5e7eb; padding: 10px 8px; text-align: left; font-size: 14px; }
          th { font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #6b7280; }
          .totals { margin-top: 18px; display: grid; gap: 6px; justify-content: end; }
          .totals div { font-size: 14px; }
          .grand { font-size: 20px; font-weight: 700; }
        </style>
      </head>
      <body>
        <div class="invoice-header">
          <div class="brand">
            <img src="${ynfLogo}" alt="YNF Deals" />
            <div>
              <div class="company">Bharuchi Corp</div>
              <div class="company-sub">YNF Deals<br />bharuchicorp@gmail.com</div>
            </div>
          </div>
          <div class="invoice-title">
            <h1>Invoice #${order.id}</h1>
            <div class="meta">Bharuchi Corp</div>
          </div>
        </div>
        <div class="meta">
          Buyer: ${order.employee_name || '—'}<br />
          Status: ${order.status || '—'}<br />
          Payment: ${order.payment_method || '—'}<br />
          Date: ${fmtDt(order.submitted_at || order.created_at)}<br />
          ${order.notes ? `Notes: ${order.notes}` : ''}
        </div>
        <table>
          <thead>
            <tr>
              <th>Product</th>
              <th>Qty</th>
              <th>Unit Price</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>${lineRows}</tbody>
        </table>
        <div class="totals">
          <div>Subtotal: $${Number(order.subtotal || 0).toFixed(2)}</div>
          <div>Discount: $${Number(order.discount_amount || 0).toFixed(2)}</div>
          <div class="grand">Total: $${Number(order.total_amount || 0).toFixed(2)}</div>
        </div>
        <script>window.onload = () => { window.print(); };</script>
      </body>
      </html>
    `);
    popup.document.close();
  }

  function load() {
    setLoading(true);
    Promise.all([
      fetchApi(`/api/in_house_sales?q=${encodeURIComponent(q)}`).catch(() => ({ rows: [], summary: {}, by_employee: [] })),
      fetchApi('/api/inventory?low_stock=3&active=all&compact=1').catch(() => ({ rows: [] })),
      fetchApi('/api/in_house_orders').catch(() => ({ rows: [], summary: {} })),
      fetchApi('/api/in_house_buyers').catch(() => ({ rows: [] })),
    ])
      .then(([salesData, inventoryData, ordersResult, buyerProfilesResult]) => {
        setData(salesData || { rows: [], summary: {}, by_employee: [], employees: [] });
        setProducts(inventoryData.rows || []);
        setOrdersData(ordersResult || { rows: [], summary: {} });
        setBuyerProfiles(buyerProfilesResult?.rows || []);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  const productSearchText = normalizeText(form.product_query);
  const barcodeSearchText = normalizeText(form.barcode);
  const hasProductSearch = productSearchText.length >= 2 || barcodeSearchText.length >= 3;

  const selectedProduct = useMemo(() => (
    products.find((product) => String(product.id) === String(form.product_id))
    || products.find((product) => String(product.barcode || '').trim() && String(product.barcode).trim() === String(form.barcode).trim())
    || products.find((product) => String(product.default_code || '').trim() && String(product.default_code).trim().toLowerCase() === String(form.barcode).trim().toLowerCase())
    || (productSearchText ? products.find((product) => (
      normalizeText(product.name) === productSearchText
      || normalizeText(product.barcode) === productSearchText
      || normalizeText(product.default_code) === productSearchText
    )) : null)
    || null
  ), [form.barcode, form.product_id, productSearchText, products]);

  const employeeOptions = data.employees || [];
  const selectedEmployee = useMemo(() => (
    employeeOptions.find((employee) => String(employee.id) === String(form.employee_id))
    || employeeOptions.find((employee) => normalizeText(employee.name) === normalizeText(form.employee_name))
    || null
  ), [employeeOptions, form.employee_id, form.employee_name]);
  const rows = data.rows || [];
  const summary = data.summary || {};
  const orders = ordersData.rows || [];
  const filteredOrders = useMemo(() => {
    const term = normalizeText(q);
    return orders.filter((order) => {
      const matchesEmployee = !selectedEmployeeFilter || (
        String(order.employee_id || '') === String(selectedEmployeeFilter.id || '')
        || normalizeText(order.employee_name) === normalizeText(selectedEmployeeFilter.name)
      );
      const matchesSearch = !term || [
        order.id,
        order.employee_name,
        order.payment_method,
        order.status,
        order.notes,
      ].some((value) => normalizeText(value).includes(term));
      return matchesEmployee && matchesSearch;
    });
  }, [orders, q, selectedEmployeeFilter]);
  const cartSubtotal = useMemo(() => (
    cart.reduce((sum, item) => sum + (Number(item.qty || 0) * Number(item.unit_price || 0)), 0)
  ), [cart]);
  const cartDiscount = Number(form.discount || 0);
  const cartTax = Math.max(0, (cartSubtotal - cartDiscount) * (Number(form.tax_rate || 0) / 100));
  const cartTotal = Math.max(0, cartSubtotal - cartDiscount + cartTax);
  const selectedProductSalePrice = selectedProduct ? (form.price_mode === 'cost' ? productCost(selectedProduct) : productRetail(selectedProduct)) : 0;
  const displayProducts = useMemo(() => {
    const query = normalizeText(form.product_query || form.barcode);
    if (!hasProductSearch) return [];
    return products
      .filter((product) => Number(product.qty_available ?? product.on_hand_qty ?? 0) > 0)
      .filter((product) => {
        return [
          product.name,
          product.brand,
          product.barcode,
          product.default_code,
          product.categ_name,
        ].some((value) => normalizeText(value).includes(query));
      })
      .sort((left, right) => Number(right.qty_available ?? right.on_hand_qty ?? 0) - Number(left.qty_available ?? left.on_hand_qty ?? 0))
      .slice(0, 36);
  }, [form.barcode, form.product_query, hasProductSearch, products]);
  const productSuggestions = useMemo(() => displayProducts.slice(0, 12), [displayProducts]);
  const activeReceipt = editingReceipt && receiptDraft ? receiptDraft : receipt;
  const activeReceiptSummary = useMemo(() => {
    const lines = activeReceipt?.lines || [];
    const subtotal = roundMoney(lines.reduce((sum, line) => sum + (Number(line.qty || 0) * Number(line.unit_price || 0)), 0));
    const discount = Number(activeReceipt?.discount_amount || 0);
    const tax = Number(activeReceipt?.tax_amount || 0);
    return {
      lines: lines.length,
      units: lines.reduce((sum, line) => sum + Number(line.qty || 0), 0),
      subtotal,
      total: roundMoney(Math.max(subtotal - discount, 0) + tax),
    };
  }, [activeReceipt]);
  const selectedBuyerLatestReceipt = useMemo(() => {
    if (!selectedEmployeeFilter) return null;
    return filteredOrders.find((order) => (
      String(order.employee_id || '') === String(selectedEmployeeFilter.id || '')
      || normalizeText(order.employee_name) === normalizeText(selectedEmployeeFilter.name)
    )) || null;
  }, [filteredOrders, selectedEmployeeFilter]);
  const selectedEmployeeOrderSummary = useMemo(() => {
    if (!selectedEmployeeFilter) return null;
    const employeeOrders = orders.filter((order) => (
      String(order.employee_id || '') === String(selectedEmployeeFilter.id || '')
      || normalizeText(order.employee_name) === normalizeText(selectedEmployeeFilter.name)
    ));
    return {
      orderCount: employeeOrders.length,
      total: employeeOrders.reduce((sum, order) => sum + Number(order.total_amount || 0), 0),
    };
  }, [orders, selectedEmployeeFilter]);

  useEffect(() => {
    if (!selectedProduct) return;
    setForm((current) => ({
      ...current,
      product_id: String(selectedProduct.id),
      product_query: current.product_query || selectedProduct.name || '',
      barcode: current.barcode || selectedProduct.barcode || selectedProduct.default_code || '',
      unit_price: String((current.price_mode === 'cost' ? productCost(selectedProduct) : productRetail(selectedProduct)).toFixed(2)),
    }));
  }, [selectedProduct?.id, form.price_mode]);

  useEffect(() => {
    if (!selectedEmployee) return;
    setForm((current) => ({
      ...current,
      employee_id: String(selectedEmployee.id),
      employee_name: selectedEmployee.name || current.employee_name,
    }));
  }, [selectedEmployee?.id]);

  function setField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function addToCart(product = selectedProduct, options = {}) {
    if (!product) {
      setMessage('Scan or select a product first.');
      return;
    }
    const productId = String(product.id);
    const qty = Math.max(1, Number(form.qty || 1));
    const defaultSalePrice = form.price_mode === 'cost' ? productCost(product) : productRetail(product);
    const unitPrice = form.price_mode === 'cost' ? productCost(product) : (options.useDefaultPrice || form.unit_price === '' ? defaultSalePrice : Number(form.unit_price || 0));
    setCart((current) => {
      const found = current.find((item) => String(item.product_id) === productId);
      if (found) {
        return current.map((item) => (
          String(item.product_id) === productId
            ? { ...item, qty: Number(item.qty || 0) + qty, unit_price: unitPrice }
            : item
        ));
      }
      return [
        ...current,
        {
          product_id: product.id,
          product_name: product.name,
          barcode: product.barcode || product.default_code || '',
          qty,
          unit_price: unitPrice,
          unit_cost: productCost(product),
          price_mode: form.price_mode,
          on_hand: Number(product.qty_available ?? product.on_hand_qty ?? 0),
        },
      ];
    });
    setForm((current) => ({ ...current, barcode: '', product_id: '', product_query: '', qty: '1', unit_price: '' }));
    setMessage(`Added ${product.name} to cart.`);
  }

  function updateCartItem(productId, key, value) {
    setCart((current) => current
      .map((item) => (String(item.product_id) === String(productId)
        ? { ...item, [key]: key === 'qty' || key === 'unit_price' ? Number(value || 0) : value }
        : item))
      .filter((item) => Number(item.qty || 0) > 0));
  }

  function applyPercentToCart() {
    const percent = Number(priceAdjustPercent || 0);
    if (!cart.length || !Number.isFinite(percent)) return;
    const multiplier = 1 + (percent / 100);
    setCart((current) => current.map((item) => ({
      ...item,
      unit_price: roundMoney(Number(item.unit_price || 0) * multiplier),
    })));
    setMessage(`Adjusted cart prices by ${percent >= 0 ? '+' : ''}${percent}%.`);
  }

  function buyerTypePercent(type) {
    switch (type) {
      case 'wholesale':
        return -20;
      case 'friends_family':
        return -10;
      case 'employee':
        return -15;
      case 'sample':
        return -100;
      default:
        return 0;
    }
  }

  function applyBuyerTypePreset() {
    const percent = buyerTypePercent(form.customer_type);
    setPriceAdjustPercent(String(percent));
    if (cart.length) {
      const multiplier = 1 + (percent / 100);
      setCart((current) => current.map((item) => ({
        ...item,
        unit_price: roundMoney(Math.max(0, Number(item.unit_price || 0) * multiplier)),
      })));
      setMessage(`Applied ${form.customer_type.replace(/_/g, ' ')} pricing preset (${percent >= 0 ? '+' : ''}${percent}%).`);
    }
  }

  function loadBuyerProfile(profile) {
    setForm((current) => ({
      ...current,
      employee_id: String(profile.employee_id || ''),
      employee_name: profile.buyer_name || '',
      customer_type: profile.buyer_type || 'walk_in',
      customer_phone: profile.buyer_phone || '',
      customer_email: profile.buyer_email || '',
    }));
    setSelectedEmployeeFilter({ id: profile.employee_id, name: profile.buyer_name });
    setMessage(`Loaded buyer profile for ${profile.buyer_name}.`);
  }

  function setReceiptDraftField(key, value) {
    setReceiptDraft((current) => ({ ...current, [key]: value }));
  }

  function updateReceiptLine(lineId, key, value) {
    setReceiptDraft((current) => ({
      ...current,
      lines: (current?.lines || []).map((line) => (
        Number(line.id) === Number(lineId)
          ? { ...line, [key]: key === 'qty' || key === 'unit_price' ? Number(value || 0) : value }
          : line
      )),
    }));
  }

  function removeReceiptDraftLine(lineId) {
    setReceiptDraft((current) => ({
      ...current,
      lines: (current?.lines || []).filter((line) => Number(line.id) !== Number(lineId)),
    }));
    setSplitLineIds((current) => current.filter((id) => Number(id) !== Number(lineId)));
    setSplitQtyMap((current) => {
      const next = { ...current };
      delete next[String(lineId)];
      return next;
    });
  }

  function addSelectedProductToInvoiceDraft() {
    if (!selectedProduct || !receiptDraft) return;
    const qty = Math.max(1, Number(form.qty || 1));
    const defaultPrice = form.price_mode === 'cost' ? productCost(selectedProduct) : productRetail(selectedProduct);
    const unitPrice = form.unit_price === '' ? defaultPrice : Number(form.unit_price || defaultPrice);
    setReceiptDraft((current) => ({
      ...current,
      lines: [
        ...(current?.lines || []),
        {
          id: `draft-${Date.now()}-${selectedProduct.id}`,
          product_id: selectedProduct.id,
          description: selectedProduct.name,
          product_name: selectedProduct.name,
          barcode: selectedProduct.barcode || selectedProduct.default_code || '',
          sku: selectedProduct.default_code || '',
          qty,
          unit_cost: productCost(selectedProduct),
          unit_price: unitPrice,
        },
      ],
    }));
    setMessage(`Added ${selectedProduct.name} to invoice draft.`);
  }

  async function saveReceiptEdits() {
    if (!receiptDraft?.id) return;
    setReceiptSaving(true);
    setMessage('');
    try {
      const result = await postApi('/api/in_house_orders/update', {
        id: receiptDraft.id,
        employee_name: receiptDraft.employee_name,
        payment_method: receiptDraft.payment_method,
        notes: receiptDraft.notes,
        discount_amount: Number(receiptDraft.discount_amount || 0),
        tax_amount: Number(receiptDraft.tax_amount || 0),
        buyer_type: receiptDraft.buyer_type || form.customer_type || 'walk_in',
        buyer_phone: receiptDraft.buyer_phone || '',
        buyer_email: receiptDraft.buyer_email || '',
        lines: (receiptDraft.lines || []).map((line) => ({
          id: Number.isFinite(Number(line.id)) ? Number(line.id) : 0,
          product_id: line.product_id,
          qty: Number(line.qty || 0),
          unit_price: Number(line.unit_price || 0),
          barcode: line.barcode || undefined,
          sku: line.sku || undefined,
        })),
      });
      const nextReceipt = result?.order || null;
      setReceipt(nextReceipt);
      setReceiptDraft(nextReceipt ? cloneReceiptDraft(nextReceipt) : null);
      setEditingReceipt(false);
      setMessage(`Invoice #${receiptDraft.id} updated.`);
      load();
    } catch (error) {
      setMessage(error.message || 'Could not update invoice.');
    } finally {
      setReceiptSaving(false);
    }
  }

  async function splitReceiptLines() {
    if (!receipt?.id || !splitLineIds.length) return;
    setReceiptSaving(true);
    setMessage('');
    try {
      const result = await postApi('/api/in_house_orders/split', {
        id: receipt.id,
        line_ids: splitLineIds,
        line_items: splitLineIds.map((id) => ({
          id,
          qty: Number(splitQtyMap[String(id)] || activeReceipt?.lines?.find((line) => Number(line.id) === Number(id))?.qty || 0),
        })),
      });
      const nextSource = result?.source_order || null;
      const nextSplit = result?.split_order || null;
      setReceipt(nextSource);
      setReceiptDraft(nextSource ? cloneReceiptDraft(nextSource) : null);
      setSplitLineIds([]);
      setEditingReceipt(false);
      setMessage(nextSplit?.id ? `Split complete. New invoice #${nextSplit.id} created.` : 'Split complete.');
      load();
    } catch (error) {
      setMessage(error.message || 'Could not split invoice.');
    } finally {
      setReceiptSaving(false);
    }
  }

  async function mergeCurrentInvoiceIntoTarget() {
    if (!receipt?.id || !mergeTargetId) return;
    setReceiptSaving(true);
    setMessage('');
    try {
      const result = await postApi('/api/in_house_orders/merge', {
        source_id: receipt.id,
        target_id: Number(mergeTargetId),
      });
      const nextTarget = result?.target_order || null;
      setReceipt(nextTarget);
      setReceiptDraft(nextTarget ? cloneReceiptDraft(nextTarget) : null);
      setReceiptId(nextTarget?.id || null);
      setMergeTargetId('');
      setEditingReceipt(false);
      setSplitLineIds([]);
      setSplitQtyMap({});
      setMessage(nextTarget?.id ? `Merged into invoice #${nextTarget.id}.` : 'Merge complete.');
      load();
    } catch (error) {
      setMessage(error.message || 'Could not merge invoices.');
    } finally {
      setReceiptSaving(false);
    }
  }

  async function submitCart() {
    if (!form.employee_name.trim() || !cart.length) return;
    setSaving(true);
    setMessage('');
    try {
      const orderNote = [
        `Advanced POS`,
        `Buyer type: ${form.customer_type}`,
        `Payment: ${form.payment_method}`,
        `Price mode: ${form.price_mode === 'cost' ? 'Cost price' : 'Retail price'}`,
        form.customer_phone ? `Phone: ${form.customer_phone}` : '',
        form.customer_email ? `Email: ${form.customer_email}` : '',
        cartDiscount ? `Order discount: ${fmt(cartDiscount)}` : '',
        cartTax ? `Estimated tax: ${fmt(cartTax)}` : '',
        `Order total: ${fmt(cartTotal)}`,
        form.notes ? `Notes: ${form.notes}` : '',
      ].filter(Boolean).join(' | ');
      const result = await postApi('/api/in_house_sales/checkout', {
        employee_name: form.employee_name,
        employee_id: form.employee_id || undefined,
        payment_method: form.payment_method || 'cash',
        discount_amount: Number(form.discount || 0),
        tax_amount: roundMoney(cartTax),
        buyer_type: form.customer_type,
        buyer_phone: form.customer_phone,
        buyer_email: form.customer_email,
        notes: orderNote,
        lines: cart.map((item) => ({
          product_id: item.product_id,
          barcode: item.barcode || undefined,
          qty: Number(item.qty || 1),
          unit_price: Number(item.unit_price || 0),
        })),
      });
      const receiptId = result?.receipt?.id ? ` Receipt #${result.receipt.id} created.` : '';
      setMessage(`POS sale saved: ${cart.length} item${cart.length === 1 ? '' : 's'} / ${fmt(cartTotal)}.${receiptId}`);
      if (result?.receipt?.id) loadReceipt(result.receipt.id);
      setCart([]);
      setForm((current) => ({
        ...current,
        employee_id: '',
        employee_name: '',
        customer_phone: '',
        customer_email: '',
        product_id: '',
        product_query: '',
        barcode: '',
        qty: '1',
        unit_price: '',
        discount: '0',
        tax_rate: '0',
        price_mode: 'retail',
        notes: '',
      }));
      load();
    } catch (error) {
      setMessage(error.message || 'Could not save POS sale.');
    } finally {
      setSaving(false);
    }
  }

  async function submit() {
    setSaving(true);
    setMessage('');
    try {
      const result = await postApi('/api/in_house_sales/checkout', {
        employee_name: form.employee_name,
        employee_id: form.employee_id || undefined,
        notes: form.notes,
        payment_method: form.payment_method || 'cash',
        tax_amount: roundMoney(cartTax),
        buyer_type: form.customer_type,
        buyer_phone: form.customer_phone,
        buyer_email: form.customer_email,
        lines: [{
          product_id: form.product_id || undefined,
          barcode: form.barcode || undefined,
          qty: Number(form.qty || 1),
          unit_price: form.unit_price === '' ? undefined : Number(form.unit_price || 0),
        }],
      });
      const receiptId = result?.receipt?.id ? ` Receipt #${result.receipt.id} created.` : '';
      setMessage(`In-house sale saved and inventory deducted.${receiptId}`);
      if (result?.receipt?.id) loadReceipt(result.receipt.id);
      setForm((current) => ({ ...current, barcode: '', product_id: '', product_query: '', qty: '1', unit_price: '', notes: '' }));
      load();
    } catch (error) {
      setMessage(error.message || 'Could not save in-house sale.');
    } finally {
      setSaving(false);
    }
  }
  const orderCols = [
    { label: 'Order #' },
    { label: 'When' },
    { label: 'Buyer' },
    { label: 'Status' },
    { label: 'Payment' },
    { label: 'Lines', align: 'right' },
    { label: 'Units', align: 'right' },
    { label: 'Total', align: 'right' },
    { label: 'Invoice', align: 'right' },
  ];
  const cartUnits = cart.reduce((sum, item) => sum + Number(item.qty || 0), 0);
  const latestOrder = orders[0] || null;
  const quickBuyerCount = buyerProfiles.length || (data.by_employee || []).length || 0;
  const panelStyle = {
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-xl)',
    background: '#FFFFFF',
    overflow: 'hidden',
  };
  const panelHeaderStyle = {
    padding: '12px 14px',
    borderBottom: '1px solid var(--border-subtle)',
    display: 'flex',
    justifyContent: 'space-between',
    gap: 12,
    alignItems: 'center',
  };
  const eyebrowStyle = {
    fontSize: 11,
    fontWeight: 900,
    color: 'var(--text-secondary)',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
  };
  const softChipStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 10px',
    borderRadius: 999,
    border: '1px solid var(--border-default)',
    background: 'var(--bg-surface-secondary)',
    fontSize: 12,
    fontWeight: 700,
    color: 'var(--text-secondary)',
  };

  return (
    <div style={{ display: 'grid', gap: 18 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10 }}>
        <KpiCard label="Orders" value={ordersData.summary?.order_count ?? orders.length} />
        <KpiCard label="Buyers" value={summary.employee_count ?? 0} />
        <KpiCard label="Units" value={fmtQty(summary.units_sold ?? 0)} />
        <KpiCard label="Approved" value={fmt(ordersData.summary?.approved_value ?? 0)} color="var(--accent-emerald)" />
        <KpiCard label="Pending" value={fmt(ordersData.summary?.pending_value ?? 0)} color="var(--accent-amber)" />
        <KpiCard label="Revenue" value={fmt(summary.revenue ?? 0)} color={Number(summary.profit || 0) >= 0 ? 'var(--accent-emerald)' : 'var(--accent-coral)'} />
      </div>

      <section style={{ ...panelStyle, padding: 0 }}>
        <div style={{ padding: 16, borderBottom: '1px solid var(--border-subtle)', display: 'grid', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 12, alignItems: 'start' }}>
            <div style={{ display: 'grid', gap: 6 }}>
              <div style={eyebrowStyle}>In-House POS</div>
              <div style={{ fontSize: 28, lineHeight: 1.04, fontWeight: 800, color: 'var(--text-primary)' }}>Counter checkout, invoice drafting, and buyer history in one terminal.</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', maxWidth: 860 }}>
                This workspace is optimized for barcode-first selling. Build the cart in the middle, browse products on the left, and keep buyer and invoice context in a narrow operational rail.
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              <GhostBtn onClick={load}>Refresh</GhostBtn>
              {receiptId ? <GhostBtn onClick={() => loadReceipt(receiptId)}>{receiptLoading ? 'Loading invoice...' : `Invoice #${receiptId}`}</GhostBtn> : null}
              {!receiptId && selectedBuyerLatestReceipt ? <GhostBtn onClick={() => loadReceipt(selectedBuyerLatestReceipt.id)}>{receiptLoading ? 'Loading invoice...' : `Latest #${selectedBuyerLatestReceipt.id}`}</GhostBtn> : null}
              {receipt ? <PrimaryBtn onClick={() => printReceipt(receipt)}>Print Invoice</PrimaryBtn> : null}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1.4fr 90px 110px 150px 150px 150px', gap: 10 }}>
            <label style={commandFieldStyle}>
              <span style={commandLabelStyle}>Scan barcode / SKU</span>
              <input
                value={form.barcode}
                onChange={(e) => setField('barcode', e.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    addToCart();
                  }
                }}
                placeholder="Scan item now"
                style={commandInputStyle}
                autoFocus
              />
            </label>
            <label style={commandFieldStyle}>
              <span style={commandLabelStyle}>Search product</span>
              <input
                value={form.product_query}
                onChange={(e) => setForm((current) => ({ ...current, product_query: e.target.value, product_id: '' }))}
                placeholder="Type product name"
                style={commandInputStyle}
                list="in-house-product-list"
              />
              <datalist id="in-house-product-list">
                {productSuggestions.map((product) => (
                  <option key={product.id} value={product.name}>{product.name} - {product.barcode || product.default_code || 'no code'}</option>
                ))}
              </datalist>
            </label>
            <label style={commandFieldStyle}>
              <span style={commandLabelStyle}>Qty</span>
              <input type="number" min="1" step="1" value={form.qty} onChange={(e) => setField('qty', e.target.value)} style={commandInputStyle} />
            </label>
            <label style={commandFieldStyle}>
              <span style={commandLabelStyle}>Unit price</span>
              <input
                type="number"
                step="0.01"
                value={form.unit_price}
                onChange={(e) => setField('unit_price', e.target.value)}
                placeholder={selectedProduct ? String(selectedProductSalePrice) : form.price_mode === 'cost' ? 'Cost' : 'Retail'}
                disabled={form.price_mode === 'cost'}
                style={{
                  ...commandInputStyle,
                  background: form.price_mode === 'cost' ? 'rgba(220,38,38,0.05)' : commandInputStyle.background,
                  color: form.price_mode === 'cost' ? 'var(--accent-coral)' : commandInputStyle.color,
                  fontWeight: form.price_mode === 'cost' ? 700 : commandInputStyle.fontWeight,
                }}
              />
            </label>
            <label style={commandFieldStyle}>
              <span style={commandLabelStyle}>Buyer type</span>
              <select value={form.customer_type} onChange={(e) => setField('customer_type', e.target.value)} style={commandInputStyle}>
                <option value="walk_in">Walk-in</option>
                <option value="employee">Employee</option>
                <option value="friends_family">Friends / family</option>
                <option value="wholesale">Wholesale</option>
                <option value="sample">Sample / comp</option>
              </select>
            </label>
            <label style={commandFieldStyle}>
              <span style={commandLabelStyle}>Payment</span>
              <select value={form.payment_method} onChange={(e) => setField('payment_method', e.target.value)} style={commandInputStyle}>
                <option value="cash">Cash</option>
                <option value="card">Card</option>
                <option value="zelle">Zelle</option>
                <option value="cashapp">Cash App</option>
                <option value="venmo">Venmo</option>
                <option value="payroll">Payroll deduction</option>
                <option value="free">Free / sample</option>
              </select>
            </label>
            <label style={commandFieldStyle}>
              <span style={commandLabelStyle}>Price mode</span>
              <select value={form.price_mode} onChange={(e) => setField('price_mode', e.target.value)} style={{ ...commandInputStyle, fontWeight: 700, color: form.price_mode === 'cost' ? 'var(--accent-coral)' : 'var(--text-primary)' }}>
                <option value="retail">Retail</option>
                <option value="cost">Cost only</option>
              </select>
            </label>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr 170px 150px 120px 120px', gap: 10 }}>
            <label style={commandFieldStyle}>
              <span style={commandLabelStyle}>Buyer name</span>
              <input
                value={form.employee_name}
                onChange={(e) => setForm((current) => ({ ...current, employee_name: e.target.value, employee_id: '' }))}
                placeholder="Walk-in customer, employee, or buyer"
                style={commandInputStyle}
                list="buyer-account-list"
              />
              <datalist id="buyer-account-list">
                {employeeOptions.map((employee) => (
                  <option key={employee.id} value={employee.name}>{employee.name}</option>
                ))}
              </datalist>
            </label>
            <label style={commandFieldStyle}>
              <span style={commandLabelStyle}>Notes</span>
              <input value={form.notes} onChange={(e) => setField('notes', e.target.value)} placeholder="Optional note" style={commandInputStyle} />
            </label>
            <label style={commandFieldStyle}>
              <span style={commandLabelStyle}>Phone</span>
              <input value={form.customer_phone} onChange={(e) => setField('customer_phone', e.target.value)} placeholder="Optional" style={commandInputStyle} />
            </label>
            <label style={commandFieldStyle}>
              <span style={commandLabelStyle}>Email</span>
              <input value={form.customer_email} onChange={(e) => setField('customer_email', e.target.value)} placeholder="Optional" style={commandInputStyle} />
            </label>
            <label style={commandFieldStyle}>
              <span style={commandLabelStyle}>Discount $</span>
              <input type="number" step="0.01" min="0" value={form.discount} onChange={(e) => setField('discount', e.target.value)} style={commandInputStyle} />
            </label>
            <label style={commandFieldStyle}>
              <span style={commandLabelStyle}>Tax %</span>
              <input type="number" step="0.01" min="0" value={form.tax_rate} onChange={(e) => setField('tax_rate', e.target.value)} style={commandInputStyle} />
            </label>
          </div>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <span style={softChipStyle}>{fmtQty(cartUnits)} units</span>
            <span style={softChipStyle}>{fmt(cartTotal)} total</span>
            <span style={softChipStyle}>{quickBuyerCount} tracked buyers</span>
            <span style={softChipStyle}>{latestOrder ? `Latest invoice #${latestOrder.id}` : 'No invoices yet'}</span>
            <span style={{ ...softChipStyle, color: form.price_mode === 'cost' ? 'var(--accent-coral)' : 'var(--accent-primary)' }}>
              {form.price_mode === 'cost' ? 'Cost-price mode' : 'Retail mode'}
            </span>
            {selectedProduct ? (
              <span style={{ ...softChipStyle, color: 'var(--accent-primary)', maxWidth: 420, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                Selected: {selectedProduct.name}
              </span>
            ) : null}
            <PrimaryBtn onClick={() => addToCart()} disabled={!selectedProduct} style={{ marginLeft: 'auto' }}>Add selected</PrimaryBtn>
          </div>
        </div>

        <div style={{ padding: 16, display: 'grid', gridTemplateColumns: 'minmax(0, 1.15fr) minmax(340px, 0.72fr) 300px', gap: 16, alignItems: 'start' }}>
          <section style={{ ...panelStyle, gap: 0 }}>
            <div style={panelHeaderStyle}>
              <div>
                <div style={eyebrowStyle}>Product Browser</div>
                <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-secondary)' }}>
                  Search by barcode, SKU, brand, or product name. Use compact tiles for rapid add.
                </div>
              </div>
              <div style={{ display: 'inline-flex', border: '1px solid var(--border-default)', borderRadius: 10, overflow: 'hidden', background: '#FFFFFF' }}>
                {['tiles', 'kanban'].map((view) => (
                  <button
                    key={view}
                    type="button"
                    onClick={() => setPosView(view)}
                    style={{
                      border: 'none',
                      borderLeft: view === 'kanban' ? '1px solid var(--border-default)' : 'none',
                      padding: '8px 12px',
                      background: posView === view ? 'var(--bg-surface-secondary)' : 'transparent',
                      color: posView === view ? 'var(--accent-primary)' : 'var(--text-secondary)',
                      fontSize: 12,
                      fontWeight: 700,
                      cursor: 'pointer',
                      textTransform: 'capitalize',
                    }}
                  >
                    {view}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ padding: 14, borderBottom: '1px solid var(--border-subtle)', display: 'grid', gap: 10 }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {employeeOptions.slice(0, 8).map((employee) => {
                  const active = String(form.employee_id || '') === String(employee.id || '');
                  return (
                    <button
                      key={employee.id}
                      type="button"
                      onClick={() => setForm((current) => ({ ...current, employee_id: String(employee.id || ''), employee_name: employee.name || '' }))}
                      style={{
                        border: active ? '1px solid var(--accent-primary)' : '1px solid var(--border-default)',
                        background: active ? 'var(--bg-surface-secondary)' : '#FFFFFF',
                        color: active ? 'var(--accent-primary)' : 'var(--text-secondary)',
                        borderRadius: 10,
                        padding: '8px 10px',
                        fontSize: 12,
                        fontWeight: 700,
                        cursor: 'pointer',
                      }}
                    >
                      {employee.name}
                    </button>
                  );
                })}
              </div>
              <details style={{ border: '1px solid var(--border-subtle)', borderRadius: 12, padding: 12, background: 'var(--bg-surface-secondary)' }}>
                <summary style={{ cursor: 'pointer', fontSize: 12, fontWeight: 800, color: 'var(--text-primary)' }}>Manual product override</summary>
                <div style={{ display: 'grid', gap: 10, marginTop: 10 }}>
                  <select value={form.product_id} onChange={(e) => setField('product_id', e.target.value)} style={inputStyle}>
                    <option value="">Choose product if scan/search did not match</option>
                    {products
                      .filter((product) => !form.product_query || normalizeText(product.name).includes(normalizeText(form.product_query)))
                      .slice(0, 80)
                      .map((product) => (
                        <option key={product.id} value={product.id}>{product.name} - {product.barcode || product.default_code || 'no code'}</option>
                      ))}
                  </select>
                  {editingReceipt ? <GhostBtn onClick={addSelectedProductToInvoiceDraft} disabled={!selectedProduct}>Add to invoice draft</GhostBtn> : null}
                </div>
              </details>
            </div>

            <div
              style={{
                padding: 14,
                display: 'grid',
                gridTemplateColumns: posView === 'kanban' ? 'repeat(auto-fill, minmax(230px, 1fr))' : 'repeat(auto-fill, minmax(170px, 1fr))',
                gap: 10,
                maxHeight: 760,
                overflow: 'auto',
              }}
            >
              {displayProducts.map((product) => {
                const qty = Number(product.qty_available ?? product.on_hand_qty ?? 0);
                const retail = productRetail(product);
                const cost = productCost(product);
                const salePrice = form.price_mode === 'cost' ? cost : retail;
                return (
                  <button
                    key={product.id}
                    type="button"
                    onClick={() => addToCart(product, { useDefaultPrice: true })}
                    style={{
                      border: selectedProduct && String(selectedProduct.id) === String(product.id) ? '1px solid var(--accent-primary)' : '1px solid var(--border-default)',
                      borderRadius: 10,
                      background: '#FFFFFF',
                      padding: 12,
                      textAlign: 'left',
                      cursor: 'pointer',
                      display: 'grid',
                      gap: 8,
                      minHeight: posView === 'kanban' ? 148 : 128,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
                      <div style={{ fontSize: posView === 'kanban' ? 13.5 : 12.5, fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.25, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: posView === 'kanban' ? 3 : 2, WebkitBoxOrient: 'vertical' }}>
                        {product.name}
                      </div>
                      <span style={{ flexShrink: 0, borderRadius: 8, padding: '2px 7px', fontSize: 10, fontWeight: 800, background: qty <= 3 ? 'var(--bg-danger)' : 'var(--bg-success)', color: qty <= 3 ? 'var(--accent-coral)' : 'var(--accent-emerald)' }}>{qty}</span>
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {product.barcode || product.default_code || 'no code'}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'end' }}>
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--text-secondary)', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{form.price_mode === 'cost' ? 'Cost sale' : 'Retail'}</div>
                        <div style={{ fontSize: posView === 'kanban' ? 18 : 16, fontWeight: 800, color: 'var(--text-primary)' }}>{fmt(salePrice)}</div>
                      </div>
                      <div style={{ textAlign: 'right', fontSize: 11, color: 'var(--text-secondary)' }}>
                        <div>Cost {fmt(cost)}</div>
                        <div>{product.brand || 'No brand'}</div>
                      </div>
                    </div>
                  </button>
                );
              })}
              {!displayProducts.length ? (
                <div style={{ padding: 24, color: 'var(--text-secondary)', fontSize: 13 }}>
                  {hasProductSearch ? 'No in-stock products match this search.' : 'Scan a barcode or type at least 2 letters to show products.'}
                </div>
              ) : null}
            </div>
          </section>

          <section style={{ ...panelStyle, position: 'sticky', top: 16, gap: 0 }}>
            <div style={panelHeaderStyle}>
              <div>
                <div style={eyebrowStyle}>Active Cart</div>
                <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-secondary)' }}>
                  Checkout builder with price edits, presets, and invoice-ready totals.
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{cart.length} lines</div>
                <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--text-primary)' }}>{fmt(cartTotal)}</div>
              </div>
            </div>

            <div style={{ padding: 14, display: 'grid', gap: 12 }}>
              {selectedProduct ? (
                <div style={{ display: 'grid', gap: 6, padding: 12, borderRadius: 10, border: '1px solid var(--border-default)', background: 'var(--bg-surface-secondary)' }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{selectedProduct.name}</div>
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 11.5, color: 'var(--text-secondary)' }}>
                    <span>{selectedProduct.barcode || selectedProduct.default_code || 'No code'}</span>
                    <span>Cost {fmt(productCost(selectedProduct))}</span>
                    <span>Retail {fmt(productRetail(selectedProduct))}</span>
                    <span>On hand {fmtQty(selectedProduct.qty_available)}</span>
                  </div>
                </div>
              ) : null}

              <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 10, background: '#FFFFFF', overflow: 'hidden' }}>
                <div style={{ padding: '10px 12px', ...eyebrowStyle, borderBottom: '1px solid var(--border-subtle)' }}>Cart lines</div>
                <div style={{ maxHeight: 420, overflow: 'auto' }}>
                  {cart.length ? cart.map((item) => (
                    <div key={item.product_id} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 70px 90px', gap: 8, alignItems: 'center', padding: 12, borderTop: '1px solid var(--border-subtle)' }}>
                      <div>
                        <div style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text-primary)' }}>{item.product_name}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{item.barcode || 'No barcode'} · {fmtQty(item.on_hand)} left</div>
                        <button type="button" onClick={() => updateCartItem(item.product_id, 'qty', 0)} style={{ marginTop: 6, border: 'none', background: 'transparent', color: 'var(--accent-coral)', fontSize: 11, fontWeight: 700, padding: 0, cursor: 'pointer' }}>Remove</button>
                      </div>
                      <input type="number" min="1" step="1" value={item.qty} onChange={(e) => updateCartItem(item.product_id, 'qty', e.target.value)} style={inputStyle} />
                      <input
                        type="number"
                        step="0.01"
                        value={item.unit_price}
                        onChange={(e) => updateCartItem(item.product_id, 'unit_price', e.target.value)}
                        disabled={item.price_mode === 'cost'}
                        title={item.price_mode === 'cost' ? 'Cost-price sale is locked to cost' : 'Edit sale price'}
                        style={{
                          ...inputStyle,
                          background: item.price_mode === 'cost' ? 'rgba(220,38,38,0.05)' : inputStyle.background,
                          color: item.price_mode === 'cost' ? 'var(--accent-coral)' : inputStyle.color,
                          fontWeight: item.price_mode === 'cost' ? 700 : inputStyle.fontWeight,
                        }}
                      />
                    </div>
                  )) : <div style={{ padding: 14, color: 'var(--text-secondary)', fontSize: 13 }}>Cart is empty. Scan or search a product to start the invoice.</div>}
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto auto auto', gap: 8, alignItems: 'end' }}>
                <label>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Adjust cart by %</div>
                  <input type="number" step="0.01" value={priceAdjustPercent} onChange={(e) => setPriceAdjustPercent(e.target.value)} style={inputStyle} />
                </label>
                <GhostBtn onClick={() => setPriceAdjustPercent('10')}>+10%</GhostBtn>
                <GhostBtn onClick={() => setPriceAdjustPercent('-10')}>-10%</GhostBtn>
                <PrimaryBtn onClick={applyPercentToCart} disabled={!cart.length}>Apply</PrimaryBtn>
              </div>

              <div style={{ border: '1px solid var(--border-default)', borderRadius: 10, background: 'var(--bg-surface-secondary)', padding: 14, display: 'grid', gap: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}><span>Subtotal</span><strong>{fmt(cartSubtotal)}</strong></div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}><span>Discount</span><strong>-{fmt(cartDiscount)}</strong></div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}><span>Tax</span><strong>{fmt(cartTax)}</strong></div>
                <div style={{ borderTop: '1px solid var(--border-default)', paddingTop: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <span style={eyebrowStyle}>Total</span>
                  <strong style={{ fontSize: 28, color: 'var(--text-primary)' }}>{fmt(cartTotal)}</strong>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <PrimaryBtn onClick={submitCart} disabled={saving || !form.employee_name.trim() || !cart.length} style={{ justifyContent: 'center', minHeight: 44 }}>
                    {saving ? 'Saving...' : 'Complete checkout'}
                  </PrimaryBtn>
                  <GhostBtn onClick={() => setCart([])} style={{ justifyContent: 'center', minHeight: 44 }}>Clear cart</GhostBtn>
                </div>
              </div>
            </div>
          </section>

          <aside style={{ display: 'grid', gap: 12, position: 'sticky', top: 16 }}>
            <section style={railCardStyle}>
              <div style={eyebrowStyle}>Buyer Context</div>
              <div style={{ display: 'grid', gap: 10 }}>
                <div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>{form.employee_name || 'No buyer selected'}</div>
                  <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)' }}>
                    {(form.customer_type || 'walk_in').replace(/_/g, ' ')} · {form.customer_phone || form.customer_email || 'No contact added'}
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8 }}>
                  <div style={miniMetricStyle}>
                    <div style={eyebrowStyle}>Orders</div>
                    <div style={miniMetricValueStyle}>{selectedEmployeeOrderSummary?.orderCount || 0}</div>
                  </div>
                  <div style={miniMetricStyle}>
                    <div style={eyebrowStyle}>Spend</div>
                    <div style={miniMetricValueStyle}>{fmt(selectedEmployeeOrderSummary?.total || 0)}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <GhostBtn onClick={applyBuyerTypePreset}>Apply preset</GhostBtn>
                  {selectedBuyerLatestReceipt ? <GhostBtn onClick={() => loadReceipt(selectedBuyerLatestReceipt.id)}>Open latest</GhostBtn> : null}
                </div>
              </div>
            </section>

            {message ? (
              <div style={{ border: '1px solid var(--border-default)', borderRadius: 10, padding: '10px 12px', background: /saved|added|loaded/i.test(message) ? 'var(--bg-success)' : 'var(--bg-danger)', color: /saved|added|loaded/i.test(message) ? 'var(--accent-emerald)' : 'var(--accent-coral)', fontSize: 13, fontWeight: 600 }}>
                {message}
              </div>
            ) : null}

            <section style={railCardStyle}>
              <div style={eyebrowStyle}>Saved Buyers</div>
              <div style={{ display: 'grid', gap: 8 }}>
                {buyerProfiles.length ? buyerProfiles.slice(0, 6).map((profile) => (
                  <button
                    key={`profile-${profile.employee_id}`}
                    type="button"
                    onClick={() => loadBuyerProfile(profile)}
                    style={railButtonStyle}
                  >
                    <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{profile.buyer_name}</div>
                    <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)' }}>
                      {(profile.buyer_type || 'walk_in').replace(/_/g, ' ')} · {profile.buyer_phone || profile.buyer_email || 'No contact saved'}
                    </div>
                  </button>
                )) : <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>No saved buyer profiles.</div>}
              </div>
            </section>

            <section style={railCardStyle}>
              <div style={eyebrowStyle}>Recent Invoices</div>
              <div style={{ display: 'grid', gap: 8 }}>
                {filteredOrders.slice(0, 6).map((order) => (
                  <button
                    key={`recent-${order.id}`}
                    type="button"
                    onClick={() => loadReceipt(order.id)}
                    style={{
                      ...railButtonStyle,
                      background: receipt?.id === order.id ? 'rgba(79,70,229,0.08)' : railButtonStyle.background,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>#{order.id} · {order.employee_name || 'Buyer'}</div>
                      <div style={{ fontWeight: 800, color: 'var(--accent-amber)' }}>{fmt(order.total_amount)}</div>
                    </div>
                    <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)' }}>
                      {fmtDt(order.submitted_at || order.created_at)}
                    </div>
                  </button>
                ))}
                {!filteredOrders.length ? <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>No invoices yet.</div> : null}
              </div>
            </section>

            <section style={railCardStyle}>
              <div style={eyebrowStyle}>Top Buyers</div>
              <div style={{ display: 'grid', gap: 8 }}>
                {(data.by_employee || []).length ? (data.by_employee || []).slice(0, 6).map((row) => (
                  <button
                    key={`${row.employee_id}-${row.employee_name}`}
                    type="button"
                    onClick={() => {
                      setForm((current) => ({ ...current, employee_id: String(row.employee_id || ''), employee_name: row.employee_name || '' }));
                      setSelectedEmployeeFilter({ id: row.employee_id, name: row.employee_name });
                    }}
                    style={railButtonStyle}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <div>
                        <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{row.employee_name}</div>
                        <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)' }}>{fmtQty(row.units_sold)} units · {row.sale_count} sales</div>
                      </div>
                      <div style={{ textAlign: 'right', fontWeight: 800, color: 'var(--text-primary)' }}>{fmt(row.revenue)}</div>
                    </div>
                  </button>
                )) : <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>No POS sales yet.</div>}
              </div>
            </section>
          </aside>
        </div>
      </section>

      {receipt ? (
        <section style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)', background: 'var(--bg-panel)', overflow: 'hidden' }}>
          <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 12, fontWeight: 900, color: 'var(--text-secondary)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Invoice</div>
              <div style={{ marginTop: 4, fontSize: 16, fontWeight: 900, color: 'var(--text-primary)' }}>Invoice #{receipt.id}</div>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{receipt.employee_name || '—'}</span>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{fmtDt(receipt.submitted_at || receipt.created_at)}</span>
              <span style={{ fontSize: 12, fontWeight: 800, color: 'var(--accent-emerald)' }}>{String(receipt.status || '').toUpperCase()}</span>
              <span style={{ fontSize: 12, fontWeight: 800, color: 'var(--accent-amber)' }}>{String(receipt.payment_method || '').toUpperCase()}</span>
              <GhostBtn onClick={() => { setEditingReceipt((current) => !current); setReceiptDraft(receipt ? cloneReceiptDraft(receipt) : null); setSplitLineIds([]); setSplitQtyMap({}); }} style={{ padding: '6px 10px' }}>
                {editingReceipt ? 'Cancel Edit' : 'Edit Invoice'}
              </GhostBtn>
              <GhostBtn onClick={splitReceiptLines} disabled={!splitLineIds.length || receiptSaving} style={{ padding: '6px 10px' }}>
                {receiptSaving ? 'Working...' : `Split ${splitLineIds.length || ''} Line${splitLineIds.length === 1 ? '' : 's'}`}
              </GhostBtn>
            </div>
          </div>
          <div style={{ padding: 14, display: 'grid', gap: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 10 }}>
              <KpiCard label="Lines" value={activeReceiptSummary.lines} />
              <KpiCard label="Units" value={fmtQty(activeReceiptSummary.units)} />
              <KpiCard label="Subtotal" value={fmt(activeReceiptSummary.subtotal)} color="var(--accent-amber)" />
              <KpiCard label="Total" value={fmt(activeReceiptSummary.total)} color="var(--accent-emerald)" />
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'end', padding: 12, border: '1px solid var(--border-subtle)', borderRadius: 16, background: 'rgba(255,255,255,0.72)' }}>
              <label style={{ minWidth: 220 }}>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Merge this invoice into</div>
                <select value={mergeTargetId} onChange={(e) => setMergeTargetId(e.target.value)} style={inputStyle}>
                  <option value="">Choose target invoice</option>
                  {orders
                    .filter((order) => Number(order.id) !== Number(receipt.id) && String(order.status || '').toLowerCase() !== 'cancelled')
                    .slice(0, 80)
                    .map((order) => (
                      <option key={order.id} value={order.id}>#{order.id} · {order.employee_name || 'Buyer'} · {fmt(order.total_amount)}</option>
                    ))}
                </select>
              </label>
              <GhostBtn onClick={mergeCurrentInvoiceIntoTarget} disabled={!mergeTargetId || receiptSaving}>Merge Invoices</GhostBtn>
            </div>
            {editingReceipt ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, padding: 12, border: '1px solid var(--border-subtle)', borderRadius: 16, background: 'rgba(255,255,255,0.76)' }}>
                <label>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Buyer name</div>
                  <input value={receiptDraft?.employee_name || ''} onChange={(e) => setReceiptDraftField('employee_name', e.target.value)} style={inputStyle} />
                </label>
                <label>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Buyer type</div>
                  <select value={receiptDraft?.buyer_type || 'walk_in'} onChange={(e) => setReceiptDraftField('buyer_type', e.target.value)} style={inputStyle}>
                    <option value="walk_in">Walk-in customer</option>
                    <option value="employee">Employee</option>
                    <option value="friends_family">Friends / family</option>
                    <option value="wholesale">Wholesale</option>
                    <option value="sample">Sample / comp</option>
                  </select>
                </label>
                <label>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Phone</div>
                  <input value={receiptDraft?.buyer_phone || ''} onChange={(e) => setReceiptDraftField('buyer_phone', e.target.value)} style={inputStyle} />
                </label>
                <label>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Email</div>
                  <input value={receiptDraft?.buyer_email || ''} onChange={(e) => setReceiptDraftField('buyer_email', e.target.value)} style={inputStyle} />
                </label>
                <label>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Payment</div>
                  <select value={receiptDraft?.payment_method || 'cash'} onChange={(e) => setReceiptDraftField('payment_method', e.target.value)} style={inputStyle}>
                    <option value="cash">Cash</option>
                    <option value="card">Card</option>
                    <option value="zelle">Zelle</option>
                    <option value="cashapp">Cash App</option>
                    <option value="venmo">Venmo</option>
                    <option value="payroll">Payroll deduction</option>
                    <option value="free">Free / sample</option>
                  </select>
                </label>
                <label>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Discount $</div>
                  <input type="number" step="0.01" value={receiptDraft?.discount_amount ?? 0} onChange={(e) => setReceiptDraftField('discount_amount', e.target.value)} style={inputStyle} />
                </label>
                <label>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Tax $</div>
                  <input type="number" step="0.01" value={receiptDraft?.tax_amount ?? 0} onChange={(e) => setReceiptDraftField('tax_amount', e.target.value)} style={inputStyle} />
                </label>
                <label style={{ gridColumn: '1 / -1' }}>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Invoice notes</div>
                  <input value={receiptDraft?.notes || ''} onChange={(e) => setReceiptDraftField('notes', e.target.value)} style={inputStyle} />
                </label>
              </div>
            ) : null}
            <TableShell footer={`${activeReceiptSummary.lines || 0} invoice line${activeReceiptSummary.lines === 1 ? '' : 's'}`}>
              <Thead cols={[
                { label: 'Split' },
                { label: 'Product' },
                { label: 'Code' },
                { label: 'Qty', align: 'right' },
                { label: 'Cost', align: 'right' },
                { label: 'Price', align: 'right' },
                { label: 'Total', align: 'right' },
                { label: 'Action', align: 'right' },
              ]} />
              <tbody>
                {!(activeReceipt?.lines || []).length ? <EmptyRow cols={8} msg="No receipt lines." /> : null}
                {(activeReceipt?.lines || []).map((line) => (
                  <tr key={line.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    <td style={td}>
                      <input
                        type="checkbox"
                        disabled={!Number.isFinite(Number(line.id))}
                        checked={splitLineIds.includes(line.id)}
                        onChange={() => {
                          setSplitLineIds((current) => current.includes(line.id) ? current.filter((id) => id !== line.id) : [...current, line.id]);
                          setSplitQtyMap((current) => ({ ...current, [String(line.id)]: current[String(line.id)] || line.qty }));
                        }}
                      />
                      {splitLineIds.includes(line.id) ? (
                        <input
                          type="number"
                          min="1"
                          step="1"
                          value={splitQtyMap[String(line.id)] ?? line.qty}
                          onChange={(e) => setSplitQtyMap((current) => ({ ...current, [String(line.id)]: e.target.value }))}
                          style={{ ...inputStyle, marginTop: 6, maxWidth: 72, textAlign: 'right' }}
                        />
                      ) : null}
                    </td>
                    <td style={tdStrong}>{line.description || line.product_name || '--'}</td>
                    <td style={tdMono}>{line.barcode || line.sku || '--'}</td>
                    <td style={tdRight}>
                      {editingReceipt ? <input type="number" min="1" step="1" value={line.qty} onChange={(e) => updateReceiptLine(line.id, 'qty', e.target.value)} style={{ ...inputStyle, textAlign: 'right', maxWidth: 80 }} /> : fmtQty(line.qty)}
                    </td>
                    <td style={tdRight}>{fmt(line.unit_cost)}</td>
                    <td style={tdRight}>
                      {editingReceipt ? <input type="number" step="0.01" value={line.unit_price} onChange={(e) => updateReceiptLine(line.id, 'unit_price', e.target.value)} style={{ ...inputStyle, textAlign: 'right', maxWidth: 100 }} /> : fmt(line.unit_price)}
                    </td>
                    <td style={{ ...tdRight, color: 'var(--accent-amber)', fontWeight: 800 }}>{fmt(roundMoney(Number(line.qty || 0) * Number(line.unit_price || 0)))}</td>
                    <td style={tdRight}>
                      {editingReceipt ? <GhostBtn onClick={() => removeReceiptDraftLine(line.id)} style={{ padding: '6px 10px' }}>Remove</GhostBtn> : <span style={{ color: 'var(--text-secondary)' }}>—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableShell>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {editingReceipt ? <PrimaryBtn onClick={saveReceiptEdits} disabled={receiptSaving}>{receiptSaving ? 'Saving...' : 'Save Invoice Changes'}</PrimaryBtn> : null}
              {receipt ? <GhostBtn onClick={() => printReceipt(receipt)}>Print / Download Invoice</GhostBtn> : null}
            </div>
            {(activeReceipt?.notes || receipt?.notes) ? <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}><strong style={{ color: 'var(--text-primary)' }}>Notes:</strong> {activeReceipt?.notes || receipt?.notes}</div> : null}
          </div>
        </section>
      ) : null}

      <div style={{ display: 'grid', gap: 10 }}>
        <section style={{ ...panelStyle, gap: 10 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'end', flexWrap: 'wrap' }}>
            <div>
              <div style={eyebrowStyle}>Invoice History</div>
              <div style={{ marginTop: 4, fontSize: 14, color: 'var(--text-secondary)' }}>
                Search the saved in-house invoices and open any receipt for review or edit.
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              <SearchInput value={q} onChange={setQ} placeholder="Search order #, buyer, payment, status..." />
              <PrimaryBtn onClick={load}>Search</PrimaryBtn>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            {selectedEmployeeFilter ? (
              <>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  Showing only <strong style={{ color: 'var(--text-primary)' }}>{selectedEmployeeFilter.name}</strong>
                </div>
                <GhostBtn onClick={() => setSelectedEmployeeFilter(null)}>Show All</GhostBtn>
              </>
            ) : null}
          </div>
          <TableShell footer={`${filteredOrders.length} sale order${filteredOrders.length === 1 ? '' : 's'}${selectedEmployeeFilter ? ` for ${selectedEmployeeFilter.name}` : ''}`}>
            <Thead cols={orderCols} />
            <tbody>
                {loading || !filteredOrders.length ? <EmptyRow cols={orderCols.length} loading={loading} msg={selectedEmployeeFilter ? 'No invoices for this buyer yet.' : 'No invoices yet.'} /> : null}
              {!loading && filteredOrders.map((order) => (
                <tr
                  key={order.id}
                  style={{
                    borderTop: '1px solid var(--border-subtle)',
                    cursor: 'pointer',
                    background: receipt?.id === order.id ? 'rgba(245,158,11,0.08)' : 'transparent',
                  }}
                  onClick={() => loadReceipt(order.id)}
                >
                  <td style={{ ...tdMono, fontWeight: 800 }}>#{order.id}</td>
                  <td style={tdMono}>{fmtDt(order.submitted_at || order.created_at)}</td>
                  <td style={tdStrong}>{order.employee_name || '--'}</td>
                  <td style={td}>
                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: '4px 8px',
                      borderRadius: 999,
                      background: String(order.status || '').toLowerCase() === 'approved' ? 'rgba(16,185,129,0.10)' : 'rgba(148,163,184,0.12)',
                      color: String(order.status || '').toLowerCase() === 'approved' ? 'var(--accent-emerald)' : 'var(--text-secondary)',
                      fontSize: 11,
                      fontWeight: 800,
                      textTransform: 'uppercase',
                    }}>
                      {String(order.status || 'pending').replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td style={td}>{order.payment_method || '--'}</td>
                  <td style={tdRight}>{fmtQty(order.line_count)}</td>
                  <td style={tdRight}>{fmtQty(order.units_requested)}</td>
                  <td style={{ ...tdRight, color: 'var(--accent-amber)', fontWeight: 800 }}>{fmt(order.total_amount)}</td>
                  <td style={tdRight}>
                    <GhostBtn onClick={(event) => { event.stopPropagation(); loadReceipt(order.id); }} style={{ padding: '6px 10px' }}>
                      View invoice
                    </GhostBtn>
                  </td>
                </tr>
              ))}
            </tbody>
          </TableShell>
        </section>
      </div>
    </div>
  );
}

function normalizeText(value) {
  return String(value || '').trim().toLowerCase();
}

function roundMoney(value) {
  return Math.round(Number(value || 0) * 100) / 100;
}

function cloneReceiptDraft(order) {
  return {
    ...order,
    buyer_type: order?.buyer_type || 'walk_in',
    buyer_phone: order?.buyer_phone || '',
    buyer_email: order?.buyer_email || '',
    tax_amount: Number(order?.tax_amount || 0),
    discount_amount: Number(order?.discount_amount || 0),
    lines: Array.isArray(order?.lines) ? order.lines.map((line) => ({ ...line })) : [],
  };
}

const inputStyle = {
  background: 'var(--bg-panel)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  padding: '6px 10px',
  fontSize: 12,
  minHeight: 34,
  lineHeight: 1.2,
  width: '100%',
};
const commandFieldStyle = {
  display: 'grid',
  gap: 5,
  minWidth: 0,
};
const commandLabelStyle = {
  fontSize: 11,
  fontWeight: 800,
  color: 'var(--text-secondary)',
  letterSpacing: '0.05em',
  textTransform: 'uppercase',
};
const commandInputStyle = {
  ...inputStyle,
  minHeight: 38,
  borderRadius: 10,
  fontSize: 13,
  background: '#FFFFFF',
};
const railCardStyle = {
  border: '1px solid var(--border-default)',
  borderRadius: 12,
  background: '#FFFFFF',
  padding: 12,
  display: 'grid',
  gap: 10,
};
const railButtonStyle = {
  width: '100%',
  padding: '10px 12px',
  borderRadius: 10,
  border: '1px solid var(--border-subtle)',
  background: 'rgba(255,255,255,0.88)',
  textAlign: 'left',
  cursor: 'pointer',
};
const miniMetricStyle = {
  border: '1px solid var(--border-default)',
  borderRadius: 10,
  background: 'var(--bg-surface-secondary)',
  padding: 10,
  display: 'grid',
  gap: 6,
};
const miniMetricValueStyle = {
  fontSize: 18,
  fontWeight: 800,
  color: 'var(--text-primary)',
};
const td = { padding: '8px 14px' };
const tdStrong = { ...td, fontWeight: 800 };
const tdMono = { ...td, color: 'var(--text-secondary)', fontSize: 12, fontFamily: 'var(--font-mono)' };
const tdRight = { ...td, textAlign: 'right' };
