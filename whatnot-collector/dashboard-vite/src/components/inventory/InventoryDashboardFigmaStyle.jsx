import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Filter,
  PackagePlus,
  PanelLeftClose,
  Search,
  ScanLine,
} from 'lucide-react';

const mockInventory = [
  {
    id: 1,
    name: 'Luxury Glow Bundle',
    brand: 'YNF Beauty',
    category: 'Bundles',
    sku: 'YNF-LGB-101',
    barcode: '889104510213',
    stock: 42,
    capacity: 60,
    value: 2940,
    margin: 38,
    soldToday: 8,
    status: 'Healthy',
    usedInAuction: true,
  },
  {
    id: 2,
    name: 'Diamond Lash Vault',
    brand: 'Belle Rue',
    category: 'Beauty',
    sku: 'BEL-DLV-884',
    barcode: '883294105422',
    stock: 11,
    capacity: 50,
    value: 1210,
    margin: 29,
    soldToday: 5,
    status: 'Low Stock',
    usedInAuction: true,
  },
  {
    id: 3,
    name: 'Studio Skin Prep Kit',
    brand: 'Canvas Pro',
    category: 'Prep',
    sku: 'CNP-SSP-220',
    barcode: '771503288904',
    stock: 26,
    capacity: 40,
    value: 1735,
    margin: 41,
    soldToday: 3,
    status: 'Healthy',
    usedInAuction: false,
  },
  {
    id: 4,
    name: 'Velvet Fragrance Duo',
    brand: 'Maison Aura',
    category: 'Fragrance',
    sku: 'MAI-VFD-472',
    barcode: '992117034415',
    stock: 7,
    capacity: 28,
    value: 980,
    margin: 34,
    soldToday: 6,
    status: 'Low Stock',
    usedInAuction: true,
  },
  {
    id: 5,
    name: 'Creator Camera Clip Set',
    brand: 'Streamline',
    category: 'Accessories',
    sku: 'STM-CCS-510',
    barcode: '120443901583',
    stock: 54,
    capacity: 72,
    value: 3510,
    margin: 47,
    soldToday: 11,
    status: 'Healthy',
    usedInAuction: false,
  },
  {
    id: 6,
    name: 'Flash Sale Pick Tray',
    brand: 'YNF Logistics',
    category: 'Ops',
    sku: 'YNF-FSP-908',
    barcode: '441903210854',
    stock: 18,
    capacity: 36,
    value: 760,
    margin: 24,
    soldToday: 2,
    status: 'Medium',
    usedInAuction: false,
  },
];

const alertOptions = ['All', 'Low Stock', 'Healthy', 'Used in Auction'];

function cn(...classes) {
  return classes.filter(Boolean).join(' ');
}

function currency(value) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
}

function statusTone(item) {
  const ratio = item.stock / item.capacity;
  if (item.status === 'Low Stock' || ratio <= 0.3) {
    return {
      badge: 'bg-amber-50 text-amber-700',
      bar: 'bg-amber-500',
    };
  }
  if (item.status === 'Medium' || ratio <= 0.55) {
    return {
      badge: 'bg-stone-100 text-stone-600',
      bar: 'bg-stone-400',
    };
  }
  return {
    badge: 'bg-emerald-50 text-emerald-700',
    bar: 'bg-emerald-500',
  };
}

function KPI({ label, value }) {
  return (
    <div className="rounded-3xl bg-white px-5 py-5 shadow-[0_8px_24px_rgba(15,23,42,0.05)]">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">{value}</div>
    </div>
  );
}

function FilterSection({ title, children }) {
  return (
    <div className="space-y-3">
      <div className="text-xs font-medium text-slate-400">{title}</div>
      {children}
    </div>
  );
}

function FilterList({ items, selected, onSelect }) {
  return (
    <div className="space-y-1">
      {items.map((item) => {
        const active = selected === item.label;
        return (
          <button
            key={item.label}
            onClick={() => onSelect(item.label)}
            className={cn(
              'flex w-full items-center justify-between rounded-2xl px-3 py-2 text-sm transition',
              active ? 'bg-amber-50 text-amber-700' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-950'
            )}
          >
            <span>{item.label}</span>
            <span className="text-xs text-slate-400">{item.count}</span>
          </button>
        );
      })}
    </div>
  );
}

function FilterDrawer({
  search,
  setSearch,
  brand,
  setBrand,
  category,
  setCategory,
  alert,
  setAlert,
  brandCounts,
  categoryCounts,
  alertCounts,
  onClose,
}) {
  return (
    <div className="h-full rounded-[28px] bg-white p-5 shadow-[0_20px_50px_rgba(15,23,42,0.08)] md:p-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs font-medium text-slate-400">Filters</div>
          <div className="mt-1 text-xl font-semibold tracking-tight text-slate-950">Inventory filters</div>
        </div>
        <button
          onClick={onClose}
          className="inline-flex items-center gap-2 rounded-2xl px-3 py-2 text-sm text-slate-500 transition hover:bg-slate-50 hover:text-slate-900"
        >
          <PanelLeftClose className="h-4 w-4" />
          Close
        </button>
      </div>

      <div className="mt-8 space-y-7">
        <FilterSection title="Search">
          <div className="flex items-center gap-3 rounded-2xl bg-slate-50 px-4 py-3">
            <Search className="h-4 w-4 text-slate-400" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search product, brand, or SKU"
              className="w-full bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
            />
          </div>
        </FilterSection>

        <FilterSection title="Brand">
          <FilterList items={brandCounts} selected={brand} onSelect={setBrand} />
        </FilterSection>

        <FilterSection title="Category">
          <FilterList items={categoryCounts} selected={category} onSelect={setCategory} />
        </FilterSection>

        <FilterSection title="Alerts">
          <div className="flex flex-wrap gap-2">
            {alertCounts.map((item) => {
              const active = alert === item.label;
              return (
                <button
                  key={item.label}
                  onClick={() => setAlert(item.label)}
                  className={cn(
                    'rounded-full px-3 py-2 text-sm transition',
                    active ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  )}
                >
                  {item.label}
                </button>
              );
            })}
          </div>
        </FilterSection>
      </div>
    </div>
  );
}

function InventoryRow({ item }) {
  const tone = statusTone(item);
  const progress = Math.max(6, Math.min(100, (item.stock / item.capacity) * 100));

  return (
    <motion.tr
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ backgroundColor: 'rgba(248, 250, 252, 0.9)' }}
      transition={{ duration: 0.2 }}
      className="border-t border-slate-100"
    >
      <td className="px-5 py-4">
        <div className="flex items-center gap-4">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-100 text-sm font-semibold text-slate-600">
            {item.name.slice(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-slate-950">{item.name}</div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span>{item.brand}</span>
              <span className="text-slate-300">•</span>
              <span>{item.category}</span>
            </div>
          </div>
        </div>
      </td>
      <td className="px-4 py-4">
        <div className="text-sm text-slate-700">{item.sku}</div>
        <div className="mt-1 font-mono text-xs text-slate-400">{item.barcode}</div>
      </td>
      <td className="px-4 py-4">
        <div className="w-[170px]">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium text-slate-900">{item.stock} units</span>
            <span className="text-slate-400">{item.capacity}</span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
            <div className={cn('h-full rounded-full', tone.bar)} style={{ width: `${progress}%` }} />
          </div>
        </div>
      </td>
      <td className="px-4 py-4 text-sm font-medium text-slate-900">{currency(item.value)}</td>
      <td className="px-4 py-4 text-sm text-slate-700">{item.margin}%</td>
      <td className="px-4 py-4 text-sm text-slate-700">{item.soldToday}</td>
      <td className="px-4 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className={cn('rounded-full px-2.5 py-1 text-xs font-medium', tone.badge)}>{item.status}</span>
          {item.usedInAuction && (
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">
              Used in auction
            </span>
          )}
        </div>
      </td>
      <td className="px-4 py-4">
        <div className="flex items-center gap-2">
          <button className="rounded-xl px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-100 hover:text-slate-950">
            Scan
          </button>
          <button className="rounded-xl px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-100 hover:text-slate-950">
            Adjust
          </button>
          <button className="rounded-xl px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-100 hover:text-slate-950">
            Details
          </button>
        </div>
      </td>
    </motion.tr>
  );
}

export default function InventoryDashboardFigmaStyle() {
  const [search, setSearch] = useState('');
  const [brand, setBrand] = useState('All Brands');
  const [category, setCategory] = useState('All Categories');
  const [alert, setAlert] = useState('All');
  const [filtersOpen, setFiltersOpen] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const saved = window.sessionStorage.getItem('ynf_inventory_filters_open');
    if (saved === 'true') setFiltersOpen(true);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.sessionStorage.setItem('ynf_inventory_filters_open', String(filtersOpen));
  }, [filtersOpen]);

  const brandCounts = useMemo(() => {
    const counts = mockInventory.reduce((acc, item) => {
      acc[item.brand] = (acc[item.brand] || 0) + 1;
      return acc;
    }, {});
    return [{ label: 'All Brands', count: mockInventory.length }].concat(
      Object.entries(counts).map(([label, count]) => ({ label, count }))
    );
  }, []);

  const categoryCounts = useMemo(() => {
    const counts = mockInventory.reduce((acc, item) => {
      acc[item.category] = (acc[item.category] || 0) + 1;
      return acc;
    }, {});
    return [{ label: 'All Categories', count: mockInventory.length }].concat(
      Object.entries(counts).map(([label, count]) => ({ label, count }))
    );
  }, []);

  const alertCounts = useMemo(() => {
    const counts = {
      All: mockInventory.length,
      'Low Stock': mockInventory.filter((item) => item.status === 'Low Stock').length,
      Healthy: mockInventory.filter((item) => item.status === 'Healthy').length,
      'Used in Auction': mockInventory.filter((item) => item.usedInAuction).length,
    };
    return alertOptions.map((label) => ({ label, count: counts[label] || 0 }));
  }, []);

  const filteredInventory = useMemo(() => {
    const query = search.trim().toLowerCase();
    return mockInventory.filter((item) => {
      const haystack = [item.name, item.brand, item.sku, item.category].join(' ').toLowerCase();
      if (query && !haystack.includes(query)) return false;
      if (brand !== 'All Brands' && item.brand !== brand) return false;
      if (category !== 'All Categories' && item.category !== category) return false;
      if (alert === 'Low Stock' && item.status !== 'Low Stock') return false;
      if (alert === 'Healthy' && item.status !== 'Healthy') return false;
      if (alert === 'Used in Auction' && !item.usedInAuction) return false;
      return true;
    });
  }, [alert, brand, category, search]);

  const stats = useMemo(() => {
    return {
      visibleProducts: filteredInventory.length,
      totalUnits: filteredInventory.reduce((sum, item) => sum + item.stock, 0),
      inventoryValue: filteredInventory.reduce((sum, item) => sum + item.value, 0),
      lowStockAlerts: filteredInventory.filter((item) => item.status === 'Low Stock').length,
    };
  }, [filteredInventory]);

  return (
    <div className="min-h-screen bg-[#f7f7f5] px-4 py-8 text-slate-900 md:px-6 xl:px-8">
      <div className="mx-auto max-w-[1520px]">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="space-y-8"
        >
          <section className="space-y-6">
            <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
              <div className="max-w-3xl">
                <div className="text-sm font-medium text-amber-700">YNF Deals Ops</div>
                <h1 className="mt-2 text-4xl font-semibold tracking-tight text-slate-950">
                  Enterprise Inventory Dashboard
                </h1>
                <p className="mt-3 text-base leading-7 text-slate-500">
                  Calm, operator-friendly inventory control for live selling, stock visibility, and quick product actions.
                </p>
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  onClick={() => setFiltersOpen(true)}
                  className="inline-flex items-center gap-2 rounded-2xl bg-white px-4 py-3 text-sm font-medium text-slate-700 shadow-[0_6px_18px_rgba(15,23,42,0.05)] transition hover:text-slate-950"
                >
                  <Filter className="h-4 w-4" />
                  Filters
                </button>
                <button className="inline-flex items-center gap-2 rounded-2xl bg-white px-4 py-3 text-sm font-medium text-slate-700 shadow-[0_6px_18px_rgba(15,23,42,0.05)] transition hover:text-slate-950">
                  <PackagePlus className="h-4 w-4" />
                  Add Product
                </button>
                <button className="inline-flex items-center gap-2 rounded-2xl bg-amber-600 px-4 py-3 text-sm font-medium text-white transition hover:bg-amber-700">
                  <ScanLine className="h-4 w-4" />
                  Scan Product
                </button>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <KPI label="Visible Products" value={stats.visibleProducts} />
              <KPI label="Total Units" value={stats.totalUnits} />
              <KPI label="Inventory Value" value={currency(stats.inventoryValue)} />
              <KPI label="Low Stock Alerts" value={stats.lowStockAlerts} />
            </div>

            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="w-full max-w-xl">
                <div className="flex items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-[0_6px_18px_rgba(15,23,42,0.05)]">
                  <Search className="h-4 w-4 text-slate-400" />
                  <input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search products, brands, or SKU"
                    className="w-full bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
                  />
                </div>
              </div>

              <div className="text-sm text-slate-500">
                {filteredInventory.length} products in view
              </div>
            </div>
          </section>

          <section className="rounded-[30px] bg-white px-2 py-2 shadow-[0_10px_30px_rgba(15,23,42,0.05)]">
            <div className="overflow-x-auto">
              <table className="min-w-full border-separate border-spacing-y-2">
                <thead>
                  <tr className="text-left text-xs font-medium text-slate-400">
                    <th className="px-5 py-3">Product</th>
                    <th className="px-4 py-3">SKU / Barcode</th>
                    <th className="px-4 py-3">Stock</th>
                    <th className="px-4 py-3">Value</th>
                    <th className="px-4 py-3">Margin</th>
                    <th className="px-4 py-3">Today Sold</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredInventory.map((item) => (
                    <InventoryRow key={item.id} item={item} />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </motion.div>

        {filtersOpen && (
          <>
            <motion.button
              type="button"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              onClick={() => setFiltersOpen(false)}
              className="fixed inset-0 z-40 bg-slate-950/18"
              aria-label="Close filters"
            />
            <motion.aside
              initial={{ opacity: 0, x: -24 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ type: 'spring', stiffness: 260, damping: 24 }}
              className="fixed inset-y-4 left-4 z-50 w-[min(320px,calc(100vw-2rem))]"
            >
              <FilterDrawer
                search={search}
                setSearch={setSearch}
                brand={brand}
                setBrand={setBrand}
                category={category}
                setCategory={setCategory}
                alert={alert}
                setAlert={setAlert}
                brandCounts={brandCounts}
                categoryCounts={categoryCounts}
                alertCounts={alertCounts}
                onClose={() => setFiltersOpen(false)}
              />
            </motion.aside>
          </>
        )}
      </div>
    </div>
  );
}
