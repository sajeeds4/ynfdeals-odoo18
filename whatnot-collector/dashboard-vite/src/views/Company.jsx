import { Suspense, lazy, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Building2,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Database,
  FileBarChart2,
  KeyRound,
  LayoutDashboard,
  Monitor,
  Network,
  Package2,
  PackageCheck,
  Receipt,
  Search,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  UploadCloud,
  UserCog,
  Users2,
} from 'lucide-react';
import { fetchApi, getCachedApi, getStoredCsrfToken, postApi, setCachedApi, usePolling } from '../hooks/useApi';
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line, PieChart, Pie, Legend,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell,
} from 'recharts';
import ynfLogo from '../assets/ynf-logo.svg';
import TikTokLiveSetup, { TikTokLiveHistoryPanel, archiveLabel, readStore, writeStore } from './company/TikTokLiveSetup';
import {
  fmtPct as companyFmtPct,
  fmtDt as companyFmtDt,
  clrProfit as companyClrProfit,
  clrMargin as companyClrMargin,
  FilterBar,
  SearchInput,
  SessionSelect,
  TableShell,
  Thead,
  EmptyRow,
  PrimaryBtn,
  formatSessionLabel,
} from './company/utils';

const Customers = lazy(() => import('./company/Customers'));
const SaleOrders = lazy(() => import('./company/SaleOrders'));
const TikTokShopOrders = lazy(() => import('./company/TikTokShopOrders'));
const TikTokReturns = lazy(() => import('./company/TikTokReturns'));
const CompanyInventory = lazy(() => import('./company/Inventory'));
const Settings = lazy(() => import('./company/Settings'));
const Reports = lazy(() => import('./company/Reports'));
const Prep = lazy(() => import('./company/Prep'));
const SessionDetail = lazy(() => import('./company/SessionDetail'));
const LiveFeed = lazy(() => import('./company/LiveFeed'));
const AuctionResults = lazy(() => import('./company/AuctionResults'));
const GraphsDashboard = lazy(() => import('./company/GraphsDashboard'));
const PickList = lazy(() => import('./company/PickList'));
const TikTokLivePickList = lazy(() => import('./company/TikTokLivePickList'));
const TikTokLiveSessionDetail = lazy(() => import('./company/TikTokLiveSessionDetail'));
const TikTokLiveAnalytics = lazy(() => import('./company/TikTokLiveAnalytics'));
const CompanyIntelligence = lazy(() => import('./company/CompanyIntelligence'));
const Diagnostics = lazy(() => import('./company/Diagnostics'));
const MegaDashboard = lazy(() => import('./company/MegaDashboard'));
const InHouseSales = lazy(() => import('./company/InHouseSales'));
const InHouseApprovals = lazy(() => import('./company/InHouseApprovals'));
const EmployeeManagement = lazy(() => import('./company/EmployeeManagement'));
const Purchases = lazy(() => import('./company/Purchases'));
const PackingScanner = lazy(() => import('./company/PackingScanner'));
const PackingAlerts = lazy(() => import('./company/PackingAlerts'));

const TABS = [
  { id: 'overview', label: 'Control Tower' },
  { id: 'orders', label: 'Sales Center' },
  { id: 'orders-whatnot', label: 'Whatnot Sales' },
  { id: 'orders-affiliate', label: 'Partner Orders' },
  { id: 'inventory', label: 'Inventory' },
  { id: 'purchases', label: 'Purchases' },
  { id: 'finances', label: 'Finance & Reporting' },
  { id: 'settings', label: 'System & Diagnostics' },
  { id: 'auction-results', label: 'Whatnot Auction Results' },
  { id: 'uploads-tiktok', label: 'TikTok CSV Uploads' },
  { id: 'uploads-affiliate', label: 'Partner CSV Uploads' },
  { id: 'tiktok', label: 'TikTok Sales' },
  { id: 'tiktok-live-sales', label: 'TikTok Live Auctions' },
  { id: 'tiktok-shop-sales', label: 'TikTok Shop Sales' },
  { id: 'tiktok-returns', label: 'TikTok Returns' },
  { id: 'packing-scanner', label: 'Packing Scanner' },
  { id: 'packing-alerts', label: 'Packing Alerts' },
  { id: 'staff-users', label: 'Staff Users' },
  { id: 'affiliate-accounts', label: 'Partner Accounts' },
  { id: 'affiliate-user-management', label: 'Partner Users' },
  { id: 'access-permissions', label: 'Access Control' },
  { id: 'tv-scanner-access', label: 'TV Scanner Access' },
  { id: 'tv-display-access', label: 'TV Display Access' },
  { id: 'inventory-access', label: 'Inventory Access' },
  { id: 'user-management-access', label: 'User Management Access' },
  { id: 'assigned-pricelists', label: 'Partner Pricing' },
  { id: 'employee-management', label: 'Employee Management' },
  { id: 'in-house-sales', label: 'In-House Sales' },
  { id: 'in-house-approvals', label: 'In-House Approvals' },
  { id: 'pricelists', label: 'Pricelists' },
  { id: 'prep', label: 'Product Prep' },
  { id: 'sessions', label: 'Sessions' },
  { id: 'customers', label: 'Customers' },
  { id: 'picklist', label: 'Pick List' },
  { id: 'intelligence', label: 'AI Intelligence' },
  { id: 'graphs', label: 'Charts & Indicators' },
  { id: 'diagnostics', label: 'Diagnostics' },
  { id: 'settings', label: 'Settings' },
];

const LAST_COMPANY_TAB_KEY = 'ynf_company_last_tab';
const COMPANY_SESSIONS_PATH = '/api/sessions/list?scope=company';
const COMPANY_BUYER_GROUPS_PATH = '/api/orders?scope=company&limit=250';
const COMPANY_SALE_ORDERS_OVERVIEW_PATH = '/api/sale_orders?scope=company&summary=1&limit=250';
const COMPANY_INVENTORY_OVERVIEW_PATH = '/api/inventory?low_stock=3&compact=1&limit=250';
const COMPANY_CUSTOMERS_OVERVIEW_PATH = '/api/customers?scope=company&limit=250';
  const COMPANY_REPORTS_OVERVIEW_PATH = '/api/reports/product_profit?scope=company&limit=250';

const COMPANY_NAV = [
  {
    id: 'overview',
    label: 'Overview',
    icon: LayoutDashboard,
    children: [{ id: 'overview', label: 'Overview', icon: LayoutDashboard }],
  },
  {
    id: 'orders-whatnot',
    label: 'Whatnot Sales',
    icon: Activity,
    hideChildren: true,
    children: [
      { id: 'orders-whatnot', label: 'Whatnot Sales', icon: Activity },
      { id: 'auction-results', label: 'Auction Results', icon: FileBarChart2 },
      { id: 'sessions', label: 'Sessions Info', icon: Activity },
    ],
  },
  {
    id: 'tiktok-live-sales',
    label: 'TikTok Sales',
    icon: Sparkles,
    hideChildren: true,
    children: [
      { id: 'tiktok-live-sales', label: 'TikTok Live Auctions', icon: Sparkles },
      { id: 'tiktok-shop-sales', label: 'TikTok Shop Sales', icon: Sparkles },
      { id: 'tiktok-returns', label: 'TikTok Returns', icon: Receipt },
      { id: 'tiktok-go-live', label: 'Go Live', icon: UploadCloud },
    ],
  },
  {
    id: 'packing-scanner',
    label: 'Packing Scanner',
    icon: PackageCheck,
    children: [
      { id: 'packing-scanner', label: 'Packing Scanner', icon: PackageCheck },
      { id: 'packing-alerts', label: 'Packing Alerts', icon: ShieldAlert },
    ],
  },
  {
    id: 'in-house-sales',
    label: 'Inhouse Sales',
    icon: ShoppingBag,
    children: [
      { id: 'in-house-sales', label: 'Inhouse Sales', icon: ShoppingBag },
      { id: 'employee-management', label: 'Employee Management', icon: UserCog },
      { id: 'in-house-approvals', label: 'Approvals', icon: ShieldCheck },
    ],
  },
  {
    id: 'customers',
    label: 'Customers',
    icon: Users2,
    children: [{ id: 'customers', label: 'Customers', icon: Users2 }],
  },
  {
    id: 'inventory',
    label: 'Inventory',
    icon: Package2,
    children: [{ id: 'inventory', label: 'Inventory', icon: Package2 }],
  },
  {
    id: 'purchases',
    label: 'Purchases',
    icon: ClipboardList,
    children: [{ id: 'purchases', label: 'Purchases', icon: ClipboardList }],
  },
  {
    id: 'finances',
    label: 'Finance',
    icon: BarChart3,
    children: [{ id: 'finances', label: 'Finance', icon: BarChart3 }],
  },
  {
    id: 'settings',
    label: 'System',
    icon: Settings2,
    children: [
      { id: 'diagnostics', label: 'Diagnostics', icon: ShieldAlert },
      { id: 'settings', label: 'Settings', icon: Settings2 },
      { id: 'tv-scanner-access', label: 'TV Scanner Access', icon: KeyRound },
      { id: 'tv-display-access', label: 'TV Display Access', icon: Monitor },
    ],
  },
];

const ROLE_NAV_RULES = {
  admin: {
    branches: null,
    tabs: null,
    defaultTab: 'overview',
  },
  staff: {
    branches: ['overview', 'orders-whatnot', 'tiktok-live-sales', 'packing-scanner', 'in-house-sales', 'customers', 'inventory', 'purchases', 'finances'],
    tabs: [
      'overview',
      'tiktok-go-live',
      'sessions',
      'tiktok-live-sales',
      'tiktok-returns',
      'picklist',
      'orders',
      'orders-whatnot',
      'auction-results',
      'tiktok-shop-sales',
      'packing-scanner',
      'in-house-sales',
      'inventory',
      'purchases',
      'prep',
      'pricelists',
      'customers',
    ],
    defaultTab: 'orders',
  },
};

const TAB_META = {
  overview: {
    title: 'YNF Deals Operations Dashboard',
    description: 'Track affiliate readiness, live selling activity, inventory exposure, and reconciliation risk from one operating view.',
  },
  finances: {
    title: 'Finance Reports',
    description: 'Track sales, profit, margin, fees, and product performance across Whatnot, TikTok Live, TikTok Shop, and in-house sales.',
  },
  'our-company': {
    title: 'YNF Deals Operations',
    description: 'Company-level operations are now organized under Affiliates, Channels, Operations, Inventory, Finance, and System.',
  },
  'mega-dashboard': {
    title: 'Company Performance',
    description: 'Use the company performance view for cross-channel metrics, executive KPIs, and operational action items.',
  },
  uploads: {
    title: 'CSV Uploads',
    description: 'TikTok Shop, TikTok Live, and partner sales are imported here, then normalized into the sales order layer.',
  },
  'uploads-tiktok': {
    title: 'TikTok CSV Uploads',
    description: 'Upload one TikTok Shop CSV file, plus the two TikTok Live auction sheets after the event. These sales become normalized sales orders.',
  },
  'uploads-affiliate': {
    title: 'Partner CSV Uploads',
    description: 'Upload partner sales files after partners finish selling. Partners use scanner, TV display, and inventory access during the day, then sales are attached later.',
  },
  sessions: {
    title: 'Live Sessions',
    description: 'Review live sessions, drill into timelines, and compare operational outcomes across channels.',
  },
  'auction-results-hub': {
    title: 'Channel Archive',
    description: 'Legacy channel views are kept for review. New TikTok and affiliate sales should flow through CSV uploads into unified orders.',
  },
  'auction-results': {
    title: 'Whatnot Live',
    description: 'Review Whatnot live auction outcomes, lot results, buyer issues, and downstream sales workflow.',
  },
  orders: {
    title: 'Sales Center',
    description: 'Review all revenue flows in one place: Whatnot, TikTok Shop, TikTok LIVE, partner uploads, and in-house sales.',
  },
  'orders-whatnot': {
    title: 'Whatnot Sales',
    description: 'Review sale orders created from Whatnot live streams, session winners, and auction results.',
  },
  'orders-affiliate': {
    title: 'Partner Orders',
    description: 'Review uploaded partner sales separately from Whatnot, TikTok Shop, TikTok Live, and in-house activity.',
  },
  'in-house-sales': {
    title: 'In-House Sales',
    description: 'Track internal staff purchases, spending patterns, and inventory movement linked to employee accounts.',
  },
  purchases: {
    title: 'Purchases',
    description: 'Create purchase orders from inventory, track vendor buying, and receive stock back into inventory.',
  },
  'employee-management': {
    title: 'Employee Management',
    description: 'Manage employee accounts, review internal purchase behavior, and generate mobile POS access links for staff.',
  },
  'staff-users': {
    title: 'Staff Users',
    description: 'Create staff users, manage sign-in access, and review employee purchase workflows.',
  },
  'affiliate-accounts': {
    title: 'Partner Accounts',
    description: 'Create partner accounts, assign pricing, and connect each account to users, tools, and inventory rules.',
  },
  'affiliate-user-management': {
    title: 'Partner User Management',
    description: 'Create delegated partner users and keep each login limited to the partner account, tools, channels, and inventory it needs.',
  },
  'access-permissions': {
    title: 'Access Control',
    description: 'Control who can use TV Scanner, TV Display, inventory, orders, and user-management tools.',
  },
  'tv-scanner-access': {
    title: 'TV Scanner Access',
    description: 'Grant scanner access for affiliates and staff who need barcode-driven live operations.',
  },
  'tv-display-access': {
    title: 'TV Display Access',
    description: 'Grant display access for floor screens, notes, pricing guidance, and live-selling visibility.',
  },
  'inventory-access': {
    title: 'Inventory Access',
    description: 'Expose products only after affiliate visibility rules and pricelist assignments are ready.',
  },
  'user-management-access': {
    title: 'User Management Governance',
    description: 'Control who can create users, change roles, manage affiliate users, revoke sessions, and mutate security-sensitive accounts.',
  },
  'assigned-pricelists': {
    title: 'Pricelist Assignments',
    description: 'Review which partners and users are attached to each pricing tier before inventory is exposed.',
  },
  'in-house-approvals': {
    title: 'In-House Approvals',
    description: 'Approve or reject employee mobile POS requests before they become final inventory-affecting sales.',
  },
  tiktok: {
    title: 'TikTok Upload Review',
    description: 'TikTok data is uploaded after the event and reconciled into unified sales orders.',
  },
  'tiktok-go-live': {
    title: 'Go Live',
    description: 'Create TikTok LIVE lot sheets, scan barcodes, and prepare the live session before uploading results.',
  },
  'tiktok-live-sales': {
    title: 'TikTok Live Auctions',
    description: 'Manage TikTok LIVE auction orders generated from confirmed winner tickets, inventory scans, and uploaded sheets.',
  },
  'tiktok-shop-sales': {
    title: 'TikTok Shop Sales',
    description: 'Track TikTok Shop orders separately from livestream auctions and in-house sales.',
  },
  'packing-scanner': {
    title: 'Packing Scanner',
    description: 'Scan a shipping label tracking number, verify every product barcode, and use Ctrl+O only for controlled overrides.',
  },
  'packing-alerts': {
    title: 'Packing Alerts',
    description: 'Scan tracking numbers from the affected label PDFs and stop duplicate-pack risk before packages leave the table.',
  },
  inventory: {
    title: 'Products',
    description: 'Manage product readiness, stock health, barcode data, affiliate visibility, and pricing-controlled inventory access.',
  },
  pricelists: {
    title: 'Pricelists',
    description: 'Define affiliate, staff, wholesale, and scanner price views before products are visible to users.',
  },
  accounts: {
    title: 'Partners',
    description: 'Manage partner accounts, user logins, scanner/display access, and pricelist-controlled inventory visibility.',
  },
  customers: {
    title: 'Customers',
    description: 'Link buyers across channels and review their spend, history, and order footprint in one profile view.',
  },
  picklist: {
    title: 'Pick List',
    description: 'Generate pull, packing, and shipment workflows that are easier for the operations team to execute quickly.',
  },
  prep: {
    title: 'Live Assist',
    description: 'Prepare products and live-selling workflows before affiliates or staff go on channel.',
  },
  settings: {
    title: 'System Settings',
    description: 'Manage platform fees, navigation controls, access protection, sessions, and admin controls.',
  },
  diagnostics: {
    title: 'Diagnostics',
    description: 'Inspect frontend errors, collector health, operational warnings, and support-level diagnostics.',
  },
};

const TAB_REDIRECTS = {
  live: 'sessions',
  'stream-report': 'sessions',
  reports: 'finances',
  competitor: 'graphs',
  'our-company': 'overview',
  'mega-dashboard': 'overview',
  'whatnot-sales': 'orders-whatnot',
  tiktok: 'tiktok-live-sales',
  'tiktok-sales': 'tiktok-live-sales',
  'packing-cert': 'packing-scanner',
  'customer-service': 'customers',
  'in-house-sales-menu': 'in-house-sales',
  marketplace: 'inventory',
};

const ACCOUNT_MANAGEMENT_TABS = new Set([
  'accounts',
  'staff-users',
  'affiliate-accounts',
  'affiliate-user-management',
  'access-permissions',
  'tv-scanner-access',
  'tv-display-access',
  'inventory-access',
  'user-management-access',
  'assigned-pricelists',
]);

const fmt = (n) => (n == null ? '—' : `$${Number(n).toFixed(2)}`);
const fmtK = (n) => {
  if (n == null) return '—';
  const value = Number(n);
  if (Math.abs(value) >= 1000) return `$${(value / 1000).toFixed(1)}k`;
  return `$${value.toFixed(2)}`;
};

const numberValue = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

function orderAmount(row) {
  return numberValue(row?.amount_total ?? row?.total_amount ?? row?.subtotal ?? row?.total ?? row?.order_amount ?? row?.price_total);
}

function orderProfit(row) {
  return numberValue(row?.line_profit ?? row?.linked_profit ?? row?.profit ?? row?.total_profit ?? row?.margin ?? row?.margin_amount ?? row?.profit_loss);
}

function orderGrossProfit(row) {
  return numberValue(row?.line_profit ?? row?.linked_profit ?? row?.gross_profit ?? row?.profit_before_fees);
}

function orderFees(row) {
  const explicit = numberValue(row?.order_fees ?? row?.linked_fees ?? row?.fees ?? row?.platform_fee);
  if (explicit > 0) return explicit;
  return orderAmount(row) * 0.06;
}

function orderCOGS(row) {
  const explicit = numberValue(row?.cost_total ?? row?.line_cost ?? row?.cost_of_goods ?? row?.cogs);
  if (explicit > 0) return explicit;
  const amount = orderAmount(row);
  const grossProfit = orderGrossProfit(row);
  if (amount > 0 && grossProfit) return Math.max(0, amount - grossProfit);
  return 0;
}

function orderNetProfit(row) {
  const explicit = numberValue(row?.net_profit ?? row?.profit_after_fees ?? row?.profit_loss);
  if (explicit) return explicit;
  const grossProfit = orderGrossProfit(row);
  if (grossProfit) return grossProfit - orderFees(row);
  const cogs = orderCOGS(row);
  if (cogs > 0) return orderAmount(row) - cogs - orderFees(row);
  return orderProfit(row);
}

function orderTracking(row) {
  const explicit = String(row?.tracking_number || row?.tracking || row?.tracking_id || '').trim();
  if (explicit) return explicit;
  const match = String(row?.notes || '').match(/Tracking ID:\s*([^|]+)/i);
  return String(match?.[1] || '').trim();
}

function orderExternalTikTokId(row) {
  const external = String(row?.external_order_id || row?.tiktok_order_id || row?.order_id || '').trim();
  if (external) return external;
  const match = String(row?.external_order_ref || '').match(/tiktok_(?:live|shop):([^:\s]+)/i);
  return String(match?.[1] || '').trim();
}

function orderBuyer(row) {
  return String(
    row?.whatnot_buyer_username
      || row?.buyer_username
      || row?.partner_id_name
      || row?.partner_name
      || row?.customer_name
      || row?.customer
      || '',
  ).trim();
}

function collectBranchIds(items) {
  return items.flatMap((item) => [item.id, ...(item.children ? collectBranchIds(item.children) : [])]);
}

function collectNavBranches(items) {
  return items.flatMap((item) => [
    [item.id, new Set(collectBranchIds(item.children || []))],
    ...(item.children ? collectNavBranches(item.children) : []),
  ]);
}

const NAV_BRANCH_IDS = collectNavBranches(COMPANY_NAV);

function branchActive(id, activeTab) {
  const branch = NAV_BRANCH_IDS.find(([branchId]) => branchId === id);
  if (!branch) return activeTab === id;
  return activeTab === id || branch[1].has(activeTab);
}

function SidebarNode({ item, activeTab, setActiveTab, depth = 0, collapsed = false }) {
  const Icon = item.icon;
  const active = branchActive(item.id, activeTab);
  const children = item.children || [];
  const hasRealChildren = !item.hideChildren && children.some((child) => child.id !== item.id);
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      <button
        type="button"
        onClick={() => setActiveTab(item.id)}
        className={`company-sidebar-link ${active ? 'is-active' : ''} ${depth > 0 ? 'is-child' : ''}`}
        title={collapsed ? item.label : undefined}
        style={{
          paddingLeft: collapsed ? 0 : depth > 0 ? 16 + (depth * 12) : 14,
          justifyContent: collapsed ? 'center' : undefined,
          minHeight: collapsed ? 44 : undefined,
        }}
      >
        {Icon ? <Icon size={depth > 0 ? 15 : 16} strokeWidth={2.1} /> : null}
        {!collapsed ? <span>{item.label}</span> : null}
      </button>
      {hasRealChildren && !collapsed && (active || depth > 0) ? (
        <div style={{ display: 'grid', gap: 8 }}>
          {children.map((child) => (
            <SidebarNode
              key={`${item.id}-${child.id}-${child.label}`}
              item={child}
              activeTab={activeTab}
              setActiveTab={setActiveTab}
              depth={depth + 1}
              collapsed={collapsed}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function isTikTokSession(session) {
  const streamUrl = String(session?.stream_url || session?.show_id || '').trim().toLowerCase();
  return streamUrl.startsWith('tiktok:');
}

function getOrderPlatformKey(row) {
  const value = [
    row?.source,
    row?.platform,
    row?.sales_channel,
    row?.order_source,
    row?.external_order_ref,
    row?.origin,
    row?.channel,
    row?.session_name,
    row?.notes,
  ].map((part) => String(part || '').toLowerCase()).join(' ');
  if (value.includes('tiktok_shop')) return 'tiktok_shop';
  if (value.includes('tiktok shop')) return 'tiktok_shop';
  if (value.includes('tiktok') || value.includes('tik tok')) return 'tiktok_live';
  if (value.includes('affiliate')) return 'affiliate';
  if (value.includes('in_house') || value.includes('in-house')) return 'in_house';
  return 'whatnot';
}

function isTikTokSaleOrder(row) {
  return getOrderPlatformKey(row).startsWith('tiktok');
}

function normalizeArchivedLiveIdentity(item) {
  const serverKey = Number(item?.serverSessionId || 0);
  if (serverKey > 0) return `server:${serverKey}`;
  const sequence = Number(item?.sequence || 0);
  const displayName = String(item?.displayName || '').trim().toLowerCase();
  const liveName = String(item?.liveName || '').trim().toLowerCase();
  if (sequence > 0) return `sequence:${sequence}:${displayName || liveName}`;
  return `local:${String(item?.id || '').trim()}`;
}

function mergeArchivedLiveHistory(serverRows, localRows) {
  const merged = [];
  const seen = new Set();
  [...(serverRows || []), ...(localRows || [])].forEach((item) => {
    const key = normalizeArchivedLiveIdentity(item);
    if (!key || seen.has(key)) return;
    seen.add(key);
    merged.push(item);
  });
  merged.sort((a, b) => new Date(b?.endedAt || 0).getTime() - new Date(a?.endedAt || 0).getTime());
  return merged;
}

function getSafeDate(value) {
  const dt = new Date(value || 0);
  return Number.isNaN(dt.getTime()) ? null : dt;
}

function extractOrderLotValues(row) {
  const values = new Set();
  [
    row?.lot_number,
    row?.linked_lot_numbers,
    row?.whatnot_lot_number,
  ].forEach((value) => {
    String(value || '')
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean)
      .forEach((part) => values.add(part.replace(/^#/, '')));
  });

  const notes = String(row?.notes || '');
  const noteMatch = notes.match(/(?:^|\n)Lot:\s*([^\n]+)/i);
  if (noteMatch?.[1]) {
    values.add(noteMatch[1].trim().replace(/^#/, ''));
  }

  const externalRef = String(row?.external_order_ref || '');
  const colonMatch = externalRef.match(/^tiktok_(?:live|shop):[^:]+:([^:]+)$/i);
  if (colonMatch?.[1]) {
    values.add(colonMatch[1].trim().replace(/^#/, ''));
  }
  const lotMatch = externalRef.match(/-LOT-([^-]+)$/i);
  if (lotMatch?.[1]) {
    values.add(lotMatch[1].trim().replace(/^#/, ''));
  }

  return values;
}

function TikTokLiveAuctions({ sessions, onSessionClick }) {
  const [session, setSession] = useState('');
  const [search, setSearch] = useState('');
  const [data, setData] = useState({ rows: [] });
  const [loading, setLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const tiktokSessions = useMemo(
    () => (
      [...(sessions || [])]
        .filter((candidate) => isTikTokSession(candidate))
        .sort((a, b) => {
          const aTime = new Date(a.started_at || a.start_time || a.created_at || 0).getTime();
          const bTime = new Date(b.started_at || b.start_time || b.created_at || 0).getTime();
          return bTime - aTime;
        })
    ),
    [sessions],
  );

  useEffect(() => {
    if (!tiktokSessions.length) {
      setSession('');
      return;
    }
    if (!session || !tiktokSessions.some((candidate) => String(candidate.id) === String(session))) {
      setSession(String(tiktokSessions[0].id));
    }
  }, [session, tiktokSessions]);

  useEffect(() => {
    if (!session) {
      setData({ rows: [] });
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchApi(`/api/auction_results?scope=company&session_id=${session}`)
      .then((payload) => {
        if (!cancelled) setData(payload || { rows: [] });
      })
      .catch(() => {
        if (!cancelled) setData({ rows: [] });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, refreshKey]);

  const selectedSession = useMemo(
    () => tiktokSessions.find((candidate) => String(candidate.id) === String(session)) || null,
    [session, tiktokSessions],
  );

  const rows = useMemo(() => {
    const q = String(search || '').trim().toLowerCase();
    return (data?.rows || []).filter((row) => {
      if (!q) return true;
      return (
        String(row.lot_number || '').toLowerCase().includes(q)
        || String(row.winner_username || '').toLowerCase().includes(q)
        || String(row.product_name || '').toLowerCase().includes(q)
        || String(row.sale_order_id_name || '').toLowerCase().includes(q)
      );
    });
  }, [data, search]);

  const totals = useMemo(() => (
    rows.reduce((acc, row) => {
      acc.revenue += Number(row.sale_price || 0);
      acc.cost += Number(row.cost_price || 0);
      acc.fees += Number(row.fees || 0);
      acc.profit += Number(row.profit || 0);
      return acc;
    }, { revenue: 0, cost: 0, fees: 0, profit: 0 })
  ), [rows]);

  const avgMargin = totals.revenue ? (totals.profit / totals.revenue) * 100 : null;
  const sessionLabel = useMemo(() => {
    if (!selectedSession) return 'TikTok LIVE session';
    const idx = tiktokSessions.findIndex((candidate) => String(candidate.id) === String(selectedSession.id));
    return formatSessionLabel(selectedSession, idx >= 0 ? idx : 0);
  }, [selectedSession, tiktokSessions]);

  const cols = [
    { label: 'Sold At' },
    { label: 'Lot #' },
    { label: 'Winner' },
    { label: 'Product' },
    { label: 'Sale Price', align: 'right' },
    { label: 'Cost', align: 'right' },
    { label: 'Fees', align: 'right' },
    { label: 'Profit', align: 'right' },
    { label: 'Margin', align: 'right' },
    { label: 'Sale Order' },
  ];

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
        <KpiCard label="Results" value={rows.length} />
        <KpiCard label="Revenue" value={fmt(totals.revenue)} color="var(--accent-amber)" />
        <KpiCard label="Profit" value={fmt(totals.profit)} color={companyClrProfit(totals.profit)} />
        <KpiCard label="Avg Margin" value={companyFmtPct(avgMargin)} color={companyClrMargin(avgMargin)} />
        <KpiCard label="Products Sold" value={selectedSession?.total_products_sold || 0} />
        <KpiCard label="Lots Sold" value={selectedSession?.total_lots_sold || 0} />
      </div>

      <FilterBar>
        <SessionSelect
          sessions={tiktokSessions}
          value={session}
          onChange={setSession}
          allLabel="Select TikTok LIVE Session"
        />
        <SearchInput value={search} onChange={setSearch} placeholder="Search winner, product, lot #…" />
        <PrimaryBtn onClick={() => setRefreshKey((value) => value + 1)}>Refresh</PrimaryBtn>
        {selectedSession ? (
          <button
            type="button"
            onClick={() => onSessionClick && onSessionClick(selectedSession.id)}
            className="btn-3d btn-3d-ghost"
            style={{ padding: '8px 16px' }}
          >
            Open Session
          </button>
        ) : null}
      </FilterBar>

      {selectedSession ? (
        <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)', padding: '16px 18px', display: 'grid', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: 16, fontWeight: 800, letterSpacing: '-0.02em' }}>{selectedSession.name || `TikTok Session #${selectedSession.id}`}</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 3 }}>
                {sessionLabel} · {selectedSession.stream_url || selectedSession.show_id || 'tiktok:'}
              </div>
            </div>
            <StatusPill status={selectedSession.status} />
          </div>
        </div>
      ) : null}

      <TableShell footer={`${rows.length} result${rows.length !== 1 ? 's' : ''} in this TikTok LIVE session`}>
        <Thead cols={cols} />
        <tbody>
          {(!tiktokSessions.length || loading || rows.length === 0) ? (
            <EmptyRow
              cols={cols.length}
              loading={loading}
              msg={tiktokSessions.length ? 'No TikTok LIVE auction results found for this session.' : 'No TikTok LIVE auction sessions yet.'}
            />
          ) : null}
          {!loading && rows.map((row) => (
            <tr
              key={row.id}
              style={{ borderTop: '1px solid var(--border-subtle)', cursor: onSessionClick ? 'pointer' : 'default' }}
              onClick={() => onSessionClick && selectedSession && onSessionClick(selectedSession.id)}
            >
              <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', fontSize: 12, fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>{companyFmtDt(row.sold_at)}</td>
              <td style={{ padding: '8px 14px', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>{row.lot_number || '—'}</td>
              <td style={{ padding: '8px 14px', fontWeight: 600 }}>{row.winner_username ? `@${row.winner_username}` : '—'}</td>
              <td style={{ padding: '8px 14px', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {row.product_name || <span style={{ color: 'var(--text-muted)' }}>(no scan)</span>}
              </td>
              <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 700, color: 'var(--accent-amber)' }}>{fmt(row.sale_price)}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--text-secondary)' }}>{fmt(row.cost_price)}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--text-secondary)' }}>{fmt(row.fees)}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 700, color: companyClrProfit(row.profit) }}>{fmt(row.profit)}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: companyClrMargin(row.margin_pct) }}>{companyFmtPct(row.margin_pct)}</td>
              <td style={{ padding: '8px 14px' }}>
                {row.sale_order_id
                  ? (
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        padding: '3px 8px',
                        borderRadius: 999,
                        background: 'rgba(16,185,129,0.16)',
                        color: 'var(--accent-emerald)',
                        fontSize: 11,
                        fontWeight: 700,
                        letterSpacing: '0.04em',
                      }}
                    >
                      {row.sale_order_id_name || 'Sale Order'}
                    </span>
                  )
                  : <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>No SO</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </TableShell>
    </div>
  );
}

function WorkflowGuide({ title, subtitle, steps }) {
  const storageKey = `ynf:workflow-dismissed:${title}`;
  const [dismissed, setDismissed] = useState(() => {
    try { return localStorage.getItem(storageKey) === '1'; } catch { return false; }
  });

  function dismiss() {
    setDismissed(true);
    try { localStorage.setItem(storageKey, '1'); } catch { /* noop */ }
  }

  function restore() {
    setDismissed(false);
    try { localStorage.removeItem(storageKey); } catch { /* noop */ }
  }

  if (dismissed) {
    return (
      <button
        type="button"
        onClick={restore}
        style={{
          border: 0,
          background: 'transparent',
          color: '#697386',
          fontSize: 12,
          fontWeight: 700,
          cursor: 'pointer',
          padding: '4px 0',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
        Show workflow guide
      </button>
    );
  }

  return (
    <section style={{
      border: '1px solid rgba(226,232,240,0.95)',
      borderRadius: 20,
      background: 'linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.94))',
      padding: 16,
      display: 'grid',
      gap: 12,
      position: 'relative',
    }}>
      <button
        type="button"
        onClick={dismiss}
        title="Dismiss guide"
        style={{
          position: 'absolute',
          top: 12,
          right: 14,
          width: 28,
          height: 28,
          border: '1px solid rgba(226,232,240,0.8)',
          borderRadius: 999,
          background: 'rgba(255,255,255,0.8)',
          color: '#697386',
          fontSize: 16,
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          lineHeight: 1,
        }}
      >
        ✕
      </button>
      <div>
        <div style={{ fontSize: 11, fontWeight: 900, color: '#697386', letterSpacing: '0.09em', textTransform: 'uppercase' }}>Recommended Workflow</div>
        <div style={{ marginTop: 6, fontSize: 20, fontWeight: 900, color: '#1a1f36', letterSpacing: '-0.03em' }}>{title}</div>
        {subtitle ? <div style={{ marginTop: 4, fontSize: 13, color: '#697386', lineHeight: 1.6 }}>{subtitle}</div> : null}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
        {steps.map((step, index) => (
          <div
            key={`${step.title}-${index}`}
            style={{
              border: '1px solid rgba(226,232,240,0.92)',
              borderRadius: 18,
              padding: 14,
              background: 'rgba(255,255,255,0.84)',
              display: 'grid',
              gap: 6,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                minWidth: 24,
                height: 24,
                borderRadius: 999,
                display: 'inline-grid',
                placeItems: 'center',
                background: 'rgba(245,158,11,0.14)',
                color: 'var(--accent-amber)',
                fontSize: 11,
                fontWeight: 900,
              }}>{index + 1}</span>
              <strong style={{ color: '#1a1f36', fontSize: 14 }}>{step.title}</strong>
            </div>
            <div style={{ fontSize: 12, color: '#697386', lineHeight: 1.55 }}>{step.detail}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function salesWorkflow(parentTab, childTab) {
  if (parentTab === 'whatnot') {
    if (childTab === 'picklist') {
      return {
        title: 'Whatnot shipping confirmation flow',
        subtitle: 'Upload the Whatnot label or packing-slip PDF to confirm shipped orders and automatically cancel the lots that never appeared in the final packout.',
        steps: [
          { title: 'Upload labels', detail: 'Upload the Whatnot packing-slip PDF from the finished show.' },
          { title: 'Confirm shipped orders', detail: 'Matching lots are marked paid and shipped, and customer / tracking details are attached.' },
          { title: 'Cancel missing lots', detail: 'Session orders missing from the uploaded lots are marked cancelled so pending orders do not linger.' },
        ],
      };
    }
    return {
      title: 'Whatnot sales flow',
      subtitle: 'Keep Whatnot work in order: capture the live, review the auction outcome, then confirm sales and follow-through.',
      steps: [
        { title: 'Monitor session', detail: 'Open Sessions Info to check the live stream, lot progress, and current operating state.' },
        { title: 'Review results', detail: 'Use Auction Results to verify winners, prices, and product matching from the live stream.' },
        { title: 'Upload pick list', detail: 'Use Pick List / Labels once labels are ready to confirm shipped orders and cancel missing lots.' },
        { title: 'Finalize orders', detail: 'Use Live Orders to review paid, shipped, cancelled, or repaired sales records.' },
      ],
    };
  }
  if (parentTab === 'tiktok') {
    if (childTab === 'go-live') {
      return {
        title: 'TikTok LIVE prep flow',
        subtitle: 'Prepare the lot sheet before going live so reconciliation is easy after the show ends.',
        steps: [
          { title: 'Generate lots', detail: 'Click I’m Going Live and create the lot rows for the show.' },
          { title: 'Scan barcodes', detail: 'Scan one barcode per lot. The cursor will jump to the next lot automatically.' },
          { title: 'End and reconcile', detail: 'When the live ends, move to Live Auctions and import the TikTok lot-details file.' },
        ],
      };
    }
    if (childTab === 'shop') {
      return {
        title: 'TikTok Shop flow',
        subtitle: 'TikTok Shop is a simple import-and-review process.',
        steps: [
          { title: 'Upload shop CSV', detail: 'Choose the TikTok Shop CSV file from the sales tab.' },
          { title: 'Preview match quality', detail: 'Check ready, duplicate, and unmatched rows before committing.' },
          { title: 'Import confirmed orders', detail: 'Import the sales and then review the created orders below.' },
        ],
      };
    }
    return {
      title: 'TikTok LIVE reconciliation flow',
      subtitle: 'Use the prepared lot sheet and the TikTok export together so LIVE sales match the real products sold.',
      steps: [
        { title: 'Open ended live', detail: 'Pick the ended Go Live session you just finished.' },
        { title: 'Upload TikTok details', detail: 'Upload the TikTok lot-details file. The lot map comes from the Go Live sheet.' },
        { title: 'Preview then import', detail: 'Cancelled rows stay cancelled, ready rows become sales, and duplicates are skipped.' },
      ],
    };
  }
  if (parentTab === 'in-house') {
    return {
      title: 'In-house sales flow',
      subtitle: 'Staff purchases should be quick and tightly controlled.',
      steps: [
        { title: 'Pick the staff member', detail: 'Choose the staff user first so the sale is tied to the right person.' },
        { title: 'Scan the item', detail: 'Scan or search the product and confirm the staff price.' },
        { title: 'Save the sale', detail: 'Saving creates the staff sale and deducts inventory immediately.' },
      ],
    };
  }
  if (parentTab === 'partners') {
    return {
      title: 'Partner sales flow',
      subtitle: 'Partners sell during the day, then their sales are attached later from uploaded files.',
      steps: [
        { title: 'Set pricing first', detail: 'Make sure partner pricing and inventory access are ready before sales begin.' },
        { title: 'Upload partner sales', detail: 'Use the partner-upload workflow once the partner finishes selling.' },
        { title: 'Review partner orders', detail: 'Check the partner order layer for payment, fulfillment, and reconciliation issues.' },
      ],
    };
  }
  return {
    title: 'Sales Center workflow',
    subtitle: 'Choose the channel first, then complete the work in the same order every time.',
    steps: [
      { title: 'Pick the sales channel', detail: 'Use Whatnot, TikTok, In-House, or Partners based on where the sale came from.' },
      { title: 'Process source data', detail: 'Capture live results or upload the CSVs needed for that channel.' },
      { title: 'Review and finalize', detail: 'Confirm orders, check exceptions, and move completed sales toward fulfillment.' },
    ],
  };
}

function TikTokSection({ sessions, onSessionClick }) {
  const [tab, setTab] = useState('sales');
  const tiktokSessions = useMemo(
    () => (sessions || []).filter((candidate) => isTikTokSession(candidate)),
    [sessions],
  );
  const whatnotSessions = useMemo(
    () => (sessions || []).filter((candidate) => !isTikTokSession(candidate)),
    [sessions],
  );
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'inline-flex', gap: 6, alignItems: 'center', alignSelf: 'flex-start', padding: 6, borderRadius: 999, border: '1px solid var(--border-default)', background: 'var(--bg-panel)' }}>
        {[
          { id: 'sales', label: 'TikTok Shop Sales' },
          { id: 'live-auctions', label: 'TikTok LIVE Auctions' },
          { id: 'live-orders', label: 'TikTok LIVE Sales Orders' },
          { id: 'live-picklist', label: 'TikTok Pick List' },
        ].map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            style={{
              background: tab === t.id ? 'rgba(245,158,11,0.16)' : 'transparent',
              border: '1px solid transparent',
              borderRadius: 999,
              padding: '8px 14px',
              cursor: 'pointer',
              color: tab === t.id ? 'var(--accent-amber)' : 'var(--text-secondary)',
              fontWeight: tab === t.id ? 900 : 700,
              fontSize: 13,
              boxShadow: tab === t.id ? 'inset 0 0 0 1px rgba(245,158,11,0.18)' : 'none',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div style={{ display: tab === 'sales' ? 'block' : 'none' }}>
        <TikTokShopOrders
          source="tiktok_shop"
          title="TikTok Shop Sales"
          emptyMessage="No TikTok Shop sales yet."
          showCreate={false}
          showImport={false}
        />
      </div>
      <div style={{ display: tab === 'live-auctions' ? 'block' : 'none' }}>
        <TikTokLiveAuctions sessions={sessions} onSessionClick={onSessionClick} />
      </div>
      <div style={{ display: tab === 'live-orders' ? 'block' : 'none' }}>
        <SaleOrders
          sessions={tiktokSessions}
          source="tiktok_live"
          title="TikTok LIVE Sales Orders"
        />
      </div>
      <div style={{ display: tab === 'live-picklist' ? 'block' : 'none' }}>
        <TikTokLivePickList sessions={tiktokSessions} />
      </div>
    </div>
  );
}

function SalesChannelCard({ channel, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        border: `1px solid ${active ? channel.color : 'rgba(226,232,240,0.92)'}`,
        borderRadius: 22,
        background: active ? `linear-gradient(180deg, ${channel.bg}, rgba(255,255,255,0.96))` : 'rgba(255,255,255,0.94)',
        padding: 18,
        textAlign: 'left',
        display: 'grid',
        gap: 14,
        cursor: 'pointer',
        boxShadow: active ? '0 18px 34px rgba(15,23,42,0.09)' : '0 10px 22px rgba(15,23,42,0.045)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 900, color: '#0f172a' }}>{channel.label}</div>
          <div style={{ marginTop: 4, fontSize: 12, color: '#64748b' }}>{channel.subtitle}</div>
        </div>
        <span style={{ width: 10, height: 10, borderRadius: 999, background: channel.color, boxShadow: `0 0 0 4px ${channel.bg}` }} />
      </div>
      <div>
        <div style={{ fontSize: 25, fontWeight: 950, color: channel.valueColor || '#0f172a', letterSpacing: '-0.04em' }}>{fmt(channel.revenue)}</div>
        <div style={{ marginTop: 5, display: 'flex', gap: 10, flexWrap: 'wrap', fontSize: 12, color: '#64748b' }}>
          <span>{channel.orders} orders</span>
          <span>{channel.paid} paid</span>
          <span>{channel.cancelled} cancelled</span>
        </div>
      </div>
    </button>
  );
}

function SalesExceptionCard({ title, value, detail, tone = 'amber', onClick }) {
  const tones = {
    amber: { bg: 'rgba(245,158,11,0.08)', border: 'rgba(245,158,11,0.24)', color: '#b45309' },
    red: { bg: 'rgba(239,68,68,0.07)', border: 'rgba(239,68,68,0.24)', color: '#dc2626' },
    blue: { bg: 'rgba(37,99,235,0.07)', border: 'rgba(37,99,235,0.22)', color: '#1d4ed8' },
    green: { bg: 'rgba(16,185,129,0.08)', border: 'rgba(16,185,129,0.24)', color: '#047857' },
  };
  const palette = tones[tone] || tones.amber;
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        border: `1px solid ${palette.border}`,
        borderRadius: 18,
        background: palette.bg,
        padding: '14px 16px',
        textAlign: 'left',
        display: 'grid',
        gap: 5,
        cursor: onClick ? 'pointer' : 'default',
      }}
    >
      <div style={{ fontSize: 11, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#64748b' }}>{title}</div>
      <div style={{ fontSize: 24, fontWeight: 950, color: palette.color, letterSpacing: '-0.04em' }}>{value}</div>
      <div style={{ fontSize: 12, color: '#64748b', lineHeight: 1.45 }}>{detail}</div>
    </button>
  );
}

function SalesCommandCenter({ saleOrders, inventory, buyerGroups, parentTab, childTab, setParentTab, setChildTab }) {
  const rows = saleOrders?.rows || [];
  const completed = rows.filter((row) => row.state !== 'cancel');
  const cancelled = rows.filter((row) => row.state === 'cancel');
  const paid = completed.filter((row) => String(row.payment_status || '').toLowerCase() === 'paid');
  const unpaid = completed.filter((row) => String(row.payment_status || '').toLowerCase() !== 'paid');
  const pendingFulfillment = completed.filter((row) => !['shipped', 'done', 'delivered'].includes(String(row.fulfillment_status || '').toLowerCase()));
  const revenue = completed.reduce((sum, row) => sum + orderAmount(row), 0);
  const profit = completed.reduce((sum, row) => sum + orderProfit(row), 0);
  const buyers = new Set(completed.map(orderBuyer).filter(Boolean).map((value) => value.toLowerCase())).size;
  const avgOrder = completed.length ? revenue / completed.length : 0;
  const margin = revenue ? (profit / revenue) * 100 : 0;
  const pendingSaleOrders = (buyerGroups?.rows || []).filter((row) => !row.sale_order_id).length;
  const missingCost = Number(inventory?.missing_cost_count || 0);

  const channelConfig = {
    all: { label: 'All Sales', subtitle: 'Every normalized sale', color: '#0f172a', bg: 'rgba(15,23,42,0.05)', parent: 'all', child: 'orders' },
    whatnot: { label: 'Whatnot', subtitle: 'Live orders and auction results', color: '#f59e0b', bg: 'rgba(245,158,11,0.10)', parent: 'whatnot', child: 'orders' },
    tiktok_live: { label: 'TikTok Live', subtitle: 'Lot-based live auctions', color: '#8b5cf6', bg: 'rgba(139,92,246,0.10)', parent: 'tiktok', child: 'live' },
    tiktok_shop: { label: 'TikTok Shop', subtitle: 'Catalog shop orders', color: '#2563eb', bg: 'rgba(37,99,235,0.09)', parent: 'tiktok', child: 'shop' },
    affiliate: { label: 'Partners', subtitle: 'Partner sales uploads', color: '#10b981', bg: 'rgba(16,185,129,0.09)', parent: 'partners', child: 'orders' },
    in_house: { label: 'In-House', subtitle: 'Employee and internal POS', color: '#64748b', bg: 'rgba(100,116,139,0.09)', parent: 'in-house', child: 'orders' },
  };
  const channelMap = new Map(Object.entries(channelConfig).map(([key, item]) => [key, { key, ...item, revenue: 0, profit: 0, orders: 0, paid: 0, cancelled: 0 }]));
  rows.forEach((row) => {
    const key = getOrderPlatformKey(row);
    const target = channelMap.get(key) || channelMap.get('all');
    if (row.state === 'cancel') {
      target.cancelled += 1;
    } else {
      target.revenue += orderAmount(row);
      target.profit += orderProfit(row);
      target.orders += 1;
      if (String(row.payment_status || '').toLowerCase() === 'paid') target.paid += 1;
    }
    const all = channelMap.get('all');
    if (row.state === 'cancel') all.cancelled += 1;
    else {
      all.revenue += orderAmount(row);
      all.profit += orderProfit(row);
      all.orders += 1;
      if (String(row.payment_status || '').toLowerCase() === 'paid') all.paid += 1;
    }
  });
  const channelRows = ['all', 'whatnot', 'tiktok_live', 'tiktok_shop', 'affiliate', 'in_house'].map((key) => channelMap.get(key));

  const activeKey = parentTab === 'all'
    ? 'all'
    : parentTab === 'whatnot'
      ? 'whatnot'
      : parentTab === 'partners'
        ? 'affiliate'
        : parentTab === 'in-house'
          ? 'in_house'
          : childTab === 'shop'
            ? 'tiktok_shop'
            : 'tiktok_live';

  const setChannel = (channel) => {
    setParentTab(channel.parent);
    setChildTab(channel.child);
  };

  return (
    <section style={{
      border: '1px solid rgba(226,232,240,0.96)',
      borderRadius: 28,
      background: 'linear-gradient(180deg, rgba(255,255,255,0.99), rgba(248,250,252,0.96))',
      boxShadow: '0 20px 44px rgba(15,23,42,0.06)',
      padding: 24,
      display: 'grid',
      gap: 20,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 900, color: '#64748b', letterSpacing: '0.14em', textTransform: 'uppercase' }}>Sales Command Center</div>
          <h2 style={{ margin: '6px 0 0', fontSize: 30, lineHeight: 1, letterSpacing: '-0.05em', color: '#0f172a' }}>Revenue, exceptions, and channel work in one place</h2>
          <p style={{ margin: '8px 0 0', color: '#64748b', fontSize: 14 }}>Click any metric or channel to drill into the matching sales workflow.</p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="company-ghost-btn" onClick={() => setChannel(channelConfig.whatnot)}>Whatnot</button>
          <button type="button" className="company-primary-btn" onClick={() => setChannel(channelConfig.tiktok_live)}>TikTok Live</button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
        <OverviewStatCard label="Revenue" value={fmt(revenue)} detail={`${completed.length} active orders`} tone="amber" />
        <OverviewStatCard label="Profit" value={profit ? fmt(profit) : 'Needs cost'} detail={`${margin.toFixed(1)}% margin`} tone={profit > 0 ? 'emerald' : 'coral'} />
        <OverviewStatCard label="Avg Order" value={fmt(avgOrder)} detail={`${paid.length} paid`} tone="blue" />
        <OverviewStatCard label="Customers" value={buyers} detail="Unique buyers" tone="violet" />
        <OverviewStatCard label="Pending" value={pendingFulfillment.length} detail="Needs fulfillment" tone="coral" />
        <OverviewStatCard label="Cancelled" value={cancelled.length} detail="Cancelled/refunded" tone="coral" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12 }}>
        {channelRows.map((channel) => (
          <SalesChannelCard
            key={channel.key}
            channel={channel}
            active={activeKey === channel.key}
            onClick={() => setChannel(channel)}
          />
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12 }}>
        <SalesExceptionCard title="Unpaid" value={unpaid.length} detail="Orders that need payment review" tone={unpaid.length ? 'red' : 'green'} onClick={() => setChannel(channelConfig.all)} />
        <SalesExceptionCard title="Pending SO" value={pendingSaleOrders} detail="Buyer rows waiting for sale order creation" tone={pendingSaleOrders ? 'amber' : 'green'} onClick={() => setChannel(channelConfig.whatnot)} />
        <SalesExceptionCard title="Missing Cost" value={missingCost} detail="Inventory cost gaps that can corrupt profit" tone={missingCost ? 'red' : 'green'} />
        <SalesExceptionCard title="Fulfillment" value={pendingFulfillment.length} detail="Paid or active orders not shipped yet" tone={pendingFulfillment.length ? 'amber' : 'green'} onClick={() => setChannel(channelConfig.all)} />
      </div>
    </section>
  );
}

function SalesWorkspace({ activeSection = 'orders', sessions, saleOrders, inventory, buyerGroups, customers, reportRows, onSessionClick }) {
  const initialParent = (() => {
    if (['orders-whatnot', 'sessions', 'auction-results'].includes(activeSection)) return 'whatnot';
    if (['tiktok-go-live', 'tiktok-shop-sales', 'tiktok-live-sales', 'tiktok-returns', 'uploads-tiktok', 'tiktok'].includes(activeSection)) return 'tiktok';
    if (activeSection === 'in-house-sales') return 'in-house';
    if (activeSection === 'orders-affiliate') return 'partners';
    return 'all';
  })();
  const initialChild = (() => {
    if (activeSection === 'sessions') return 'sessions';
    if (activeSection === 'auction-results') return 'whatnot-auctions';
    if (activeSection === 'tiktok-go-live') return 'go-live';
    if (activeSection === 'tiktok') return 'tiktok-auctions';
    if (activeSection === 'tiktok-shop-sales') return 'shop';
    if (activeSection === 'tiktok-live-sales') return 'tiktok-auctions';
    if (activeSection === 'tiktok-returns') return 'returns';
    if (activeSection === 'uploads-tiktok') return 'uploads';
    if (activeSection === 'orders-affiliate') return 'orders';
    return 'orders';
  })();

  const [parentTab, setParentTab] = useState(initialParent);
  const [childTab, setChildTab] = useState(initialChild);
  const [selectedArchivedLive, setSelectedArchivedLive] = useState(null);
  const [pendingTikTokLivePrint, setPendingTikTokLivePrint] = useState(null);
  const [tiktokLiveRefreshToken, setTikTokLiveRefreshToken] = useState(0);
  const tiktokPickListRef = useRef(null);

  useLayoutEffect(() => {
    setParentTab(initialParent);
    setChildTab(initialChild);
  }, [activeSection]);

  useEffect(() => {
    if (activeSection !== 'tiktok-live') return () => {};
    const syncArchivedLive = () => {
      const store = readStore();
      const history = Array.isArray(store.history) ? store.history : [];
      const applyHistory = (rows) => {
        if (!rows.length) {
          setSelectedArchivedLive(null);
          return;
        }
        setSelectedArchivedLive((current) => {
          if (current && rows.some((item) => String(item.id) === String(current.id))) {
            return rows.find((item) => String(item.id) === String(current.id)) || current;
          }
          return rows[0];
        });
      };

      fetchApi('/api/tiktok_live_sessions?limit=120')
        .then((data) => {
          const serverRows = Array.isArray(data?.rows) ? data.rows : [];
          if (!serverRows.length) return;
          const merged = serverRows;
          applyHistory(merged);
        })
        .catch(() => {
          applyHistory(history);
        });
    };
    syncArchivedLive();
    window.addEventListener('ynf:tiktok-live-store-updated', syncArchivedLive);
    window.addEventListener('storage', syncArchivedLive);
    return () => {
      window.removeEventListener('ynf:tiktok-live-store-updated', syncArchivedLive);
      window.removeEventListener('storage', syncArchivedLive);
    };
  }, [activeSection]);

  const tiktokSessions = useMemo(
    () => (sessions || []).filter((candidate) => isTikTokSession(candidate)),
    [sessions],
  );
  const whatnotSessions = useMemo(
    () => (sessions || []).filter((candidate) => !isTikTokSession(candidate)),
    [sessions],
  );

  const topTabs = [
    { id: 'all', label: 'Sales Center' },
    { id: 'whatnot', label: 'Whatnot' },
    { id: 'tiktok', label: 'TikTok' },
    { id: 'in-house', label: 'In-House' },
    { id: 'partners', label: 'Partners' },
  ];

  const childTabs = {
    whatnot: [
      { id: 'whatnot-auctions', label: 'Whatnot Auctions' },
      { id: 'orders', label: 'Sales' },
      { id: 'picklist', label: 'Pick List / Labels' },
      { id: 'confirmed', label: 'Confirmed Sales' },
      { id: 'cancelled', label: 'Cancelled Sales' },
    ],
    tiktok: [
      { id: 'tiktok-auctions', label: 'TikTok Live Auctions' },
      { id: 'shop', label: 'TikTok Shop Sales' },
      { id: 'confirmed', label: 'Confirmed Sales' },
      { id: 'cancelled', label: 'Cancelled Sales' },
      { id: 'returns', label: 'Returns' },
      { id: 'data-analysis', label: 'Data Analysis' },
    ],
    'in-house': [
      { id: 'orders', label: 'In-House Sales' },
    ],
    partners: [
      { id: 'orders', label: 'Partner Orders' },
    ],
  };

  useEffect(() => {
    const tabs = childTabs[parentTab];
    if (!tabs?.some((tab) => tab.id === childTab)) {
      setChildTab(tabs?.[0]?.id || 'orders');
    }
  }, [parentTab, childTab]);

  const showParentTabs = false;
  const showChildTabs = ['whatnot', 'tiktok'].includes(parentTab);

  function handleArchivedLivePrint(item) {
    setParentTab('tiktok');
    setChildTab('live');
    setSelectedArchivedLive(item);
    setPendingTikTokLivePrint({
      id: String(item?.id || ''),
      mode: 'both',
      token: `${String(item?.id || '')}-${Date.now()}`,
    });
    window.requestAnimationFrame(() => {
      tiktokPickListRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {activeSection === 'orders' ? (
        <SalesCommandCenter
          saleOrders={saleOrders}
          inventory={inventory}
          buyerGroups={buyerGroups}
          parentTab={parentTab}
          childTab={childTab}
          setParentTab={setParentTab}
          setChildTab={setChildTab}
        />
      ) : null}

      {showParentTabs ? (
        <div style={{ display: 'inline-flex', gap: 6, alignItems: 'center', alignSelf: 'flex-start', padding: 6, borderRadius: 999, border: '1px solid var(--border-default)', background: 'var(--bg-panel)', flexWrap: 'wrap' }}>
          {topTabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setParentTab(tab.id)}
              style={{
                background: parentTab === tab.id ? 'rgba(245,158,11,0.16)' : 'transparent',
                border: '1px solid transparent',
                borderRadius: 999,
                padding: '8px 14px',
                cursor: 'pointer',
                color: parentTab === tab.id ? 'var(--accent-amber)' : 'var(--text-secondary)',
                fontWeight: parentTab === tab.id ? 900 : 700,
                fontSize: 13,
                boxShadow: parentTab === tab.id ? 'inset 0 0 0 1px rgba(245,158,11,0.18)' : 'none',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      ) : null}

      {showChildTabs && childTabs[parentTab]?.length ? (
        <div style={{ display: 'inline-flex', gap: 6, alignItems: 'center', alignSelf: 'flex-start', padding: 6, borderRadius: 999, border: '1px solid var(--border-default)', background: 'rgba(255,255,255,0.86)', flexWrap: 'wrap' }}>
          {childTabs[parentTab].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setChildTab(tab.id)}
              style={{
                background: childTab === tab.id ? 'rgba(26,31,54,0.08)' : 'transparent',
                border: '1px solid transparent',
                borderRadius: 999,
                padding: '7px 13px',
                cursor: 'pointer',
                color: childTab === tab.id ? 'var(--text-primary)' : 'var(--text-secondary)',
                fontWeight: childTab === tab.id ? 900 : 700,
                fontSize: 12,
                boxShadow: childTab === tab.id ? 'inset 0 0 0 1px rgba(26,31,54,0.08)' : 'none',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      ) : null}

      {parentTab === 'all' ? (
        <Suspense fallback={<CompanyLazyFallback label="Loading sales..." />}>
          <SaleOrders sessions={sessions} />
        </Suspense>
      ) : null}

      {parentTab === 'whatnot' && childTab === 'orders' ? (
        <Suspense fallback={<CompanyLazyFallback label="Loading Whatnot sales..." />}>
          <SaleOrders sessions={whatnotSessions} source="whatnot" title="Whatnot Sales" finalOnly initialOrderTab="paid" onOpenPickList={() => setChildTab('picklist')} />
        </Suspense>
      ) : null}
      {parentTab === 'whatnot' && childTab === 'picklist' ? (
        <Suspense fallback={<CompanyLazyFallback label="Loading pick list..." />}>
          <PickList sessions={whatnotSessions} />
        </Suspense>
      ) : null}
      {parentTab === 'whatnot' && childTab === 'confirmed' ? (
        <Suspense fallback={<CompanyLazyFallback label="Loading confirmed sales..." />}>
          <SaleOrders sessions={whatnotSessions} source="whatnot" title="Whatnot Confirmed Sales" finalOnly initialOrderTab="paid" />
        </Suspense>
      ) : null}
      {parentTab === 'whatnot' && childTab === 'cancelled' ? (
        <Suspense fallback={<CompanyLazyFallback label="Loading cancelled sales..." />}>
          <SaleOrders sessions={whatnotSessions} source="whatnot" title="Whatnot Cancelled Sales" finalOnly initialOrderTab="cancel" />
        </Suspense>
      ) : null}
      {parentTab === 'whatnot' && childTab === 'whatnot-auctions' ? (
        <Suspense fallback={<CompanyLazyFallback label="Loading auction results..." />}>
          <AuctionResults sessions={whatnotSessions} />
        </Suspense>
      ) : null}

      {parentTab === 'tiktok' && childTab === 'shop' ? (
        <Suspense fallback={<CompanyLazyFallback label="Loading TikTok Shop..." />}>
          <TikTokShopOrders
            source="tiktok_shop"
            title="TikTok Shop Sales"
            emptyMessage="No TikTok Shop sales yet."
            showCreate={false}
            showImport
            importTitle="Import TikTok Shop CSV"
          />
        </Suspense>
      ) : null}
      {parentTab === 'tiktok' && childTab === 'confirmed' ? (
        <Suspense fallback={<CompanyLazyFallback label="Loading TikTok confirmed sales..." />}>
          <SaleOrders
            sessions={tiktokSessions}
            source="tiktok_live"
            title="TikTok Confirmed Sales"
            finalOnly
            initialOrderTab="paid"
            rowFilter={isTikTokSaleOrder}
          />
        </Suspense>
      ) : null}
      {parentTab === 'tiktok' && childTab === 'cancelled' ? (
        <Suspense fallback={<CompanyLazyFallback label="Loading TikTok cancelled sales..." />}>
          <SaleOrders
            sessions={tiktokSessions}
            source="tiktok_live"
            title="TikTok Cancelled Sales"
            finalOnly
            initialOrderTab="cancel"
            rowFilter={isTikTokSaleOrder}
          />
        </Suspense>
      ) : null}
      {parentTab === 'tiktok' && childTab === 'returns' ? (
        <Suspense fallback={<CompanyLazyFallback label="Loading TikTok returns..." />}>
          <TikTokReturns />
        </Suspense>
      ) : null}
      {parentTab === 'tiktok' && childTab === 'data-analysis' ? (
        <Suspense fallback={<CompanyLazyFallback label="Loading TikTok analytics..." />}>
          <TikTokLiveAnalytics sessions={tiktokSessions} />
        </Suspense>
      ) : null}
      {parentTab === 'tiktok' && childTab === 'tiktok-auctions' ? (
        <div style={{ display: 'grid', gap: 14 }}>

          <TikTokLiveHistoryPanel
            selectedId={selectedArchivedLive?.id || ''}
            onSelect={setSelectedArchivedLive}
            onPrint={handleArchivedLivePrint}
            onImported={() => setTikTokLiveRefreshToken((value) => value + 1)}
            refreshToken={tiktokLiveRefreshToken}
            renderExpandedContent={(item, detailView, sharedData = {}) => (
              <div style={{ display: 'grid', gap: 14 }}>
                <Suspense fallback={<CompanyLazyFallback label="Loading TikTok live detail..." />}>
                  <TikTokLiveSessionDetail
                    archivedLive={item}
                    refreshToken={tiktokLiveRefreshToken}
                    view={detailView}
                    providedOrders={sharedData.orders}
                    providedInventory={sharedData.inventory}
                    externalLoading={sharedData.detailDataLoading}
                    initialSearch={sharedData.detailSearch}
                  />
                </Suspense>

                <div ref={tiktokPickListRef} />
                <Suspense fallback={<CompanyLazyFallback label="Loading TikTok pick list..." />}>
                  <TikTokLivePickList
                    sessions={tiktokSessions}
                    orderedDate=""
                    archiveName={archiveLabel(item)}
                    lotNumbers={(item?.rows || []).map((entry) => String(entry?.lotNo || '').trim()).filter(Boolean)}
                    autoPrintMode={pendingTikTokLivePrint?.id === String(item?.id || '') ? pendingTikTokLivePrint.mode : ''}
                    autoPrintToken={pendingTikTokLivePrint?.id === String(item?.id || '') ? pendingTikTokLivePrint.token : ''}
                    refreshToken={tiktokLiveRefreshToken}
                  />
                </Suspense>
              </div>
            )}
          />

        </div>
      ) : null}
      {parentTab === 'tiktok' && childTab === 'uploads' ? (
        <div style={{ display: 'grid', gap: 14 }}>
          <Suspense fallback={<CompanyLazyFallback label="Loading TikTok uploads..." />}>
            <TikTokShopOrders
              source="tiktok_shop"
              title="TikTok Shop CSV Upload"
              importTitle="Import TikTok Shop CSV"
              emptyMessage="No TikTok Shop CSV imports yet."
              showCreate={false}
              showImport
            />
            <TikTokShopOrders
              source="tiktok_live"
              title="TikTok Live CSV Upload"
              importTitle="Import TikTok Live CSV"
              emptyMessage="No TikTok Live CSV imports yet."
              showCreate={false}
              showImport
            />
          </Suspense>
        </div>
      ) : null}

      {parentTab === 'in-house' ? (
        <Suspense fallback={<CompanyLazyFallback label="Loading in-house sales..." />}>
          <InHouseSales />
        </Suspense>
      ) : null}

      {parentTab === 'partners' ? (
        <Suspense fallback={<CompanyLazyFallback label="Loading partner orders..." />}>
          <SaleOrders source="affiliate" title="Partner Orders" />
        </Suspense>
      ) : null}
    </div>
  );
}

function TikTokDecisionEngine({ sessions = [], saleOrders = { rows: [] }, inventory = { rows: [] }, customers = { rows: [] }, reportRows = { rows: [] } }) {
  const [analysisMode, setAnalysisMode] = useState('overview');
  const [selectedBuyer, setSelectedBuyer] = useState('');
  const [returnRows, setReturnRows] = useState([]);
  const [returnSummary, setReturnSummary] = useState({});
  const money = (value) => `$${numberValue(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const rows = (saleOrders?.rows || []).filter((row) => getOrderPlatformKey(row) === 'tiktok_live');
  const confirmedRows = rows.filter((row) => row.state !== 'cancel');
  const cancelledRows = rows.filter((row) => row.state === 'cancel');
  const unconfirmedRows = rows.filter((row) => row.state !== 'cancel' && row.payment_status && row.payment_status !== 'paid');
  const revenue = confirmedRows.reduce((sum, row) => sum + orderAmount(row), 0);
  const totalFees = confirmedRows.reduce((sum, row) => sum + orderFees(row), 0);
  const totalCogs = confirmedRows.reduce((sum, row) => sum + orderCOGS(row), 0);
  const netProfit = confirmedRows.reduce((sum, row) => sum + orderNetProfit(row), 0);
  const netMarginPct = revenue ? (netProfit / revenue) * 100 : 0;
  const aov = confirmedRows.length ? revenue / confirmedRows.length : 0;
  const activeSessions = (sessions || []).filter((session) => String(session.status || '').toLowerCase() === 'live').length;
  const customerMap = new Map((customers?.rows || []).map((customer) => [String(customer.id || customer.customer_id || ''), customer]));
  useEffect(() => {
    let cancelled = false;
    fetchApi('/api/v2/integrations/tiktok-shop/returns?limit=500')
      .then((data) => {
        if (cancelled) return;
        setReturnRows(Array.isArray(data?.rows) ? data.rows : []);
        setReturnSummary(data?.summary || {});
      })
      .catch(() => {
        if (cancelled) return;
        setReturnRows([]);
        setReturnSummary({});
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const dateValue = (row) => getSafeDate(row?.date_order || row?.ordered_at || row?.created_at);
  const rowRegion = (row) => {
    const customer = customerMap.get(String(row?.customer_id || '')) || {};
    return String(
      row?.state_name
      || row?.partner_state
      || row?.shipping_state
      || customer.state
      || customer.region
      || customer.shipping_state
      || '',
    ).trim();
  };

  const orderByTikTokId = new Map();
  const orderBySaleId = new Map();
  confirmedRows.forEach((row) => {
    const tiktokId = orderExternalTikTokId(row);
    if (tiktokId) orderByTikTokId.set(tiktokId, row);
    if (row?.id != null) orderBySaleId.set(String(row.id), row);
    if (row?.sale_order_id != null) orderBySaleId.set(String(row.sale_order_id), row);
  });
  const matchedReturnRows = (returnRows || [])
    .map((row) => {
      const saleId = String(row.sale_order_id || '').trim();
      const orderId = String(row.order_id || row.tiktok_order_id || '').trim();
      const external = String(row.external_order_ref || '').match(/tiktok_(?:live|shop):([^:\s]+)/i)?.[1] || '';
      const saleOrder = (saleId && orderBySaleId.get(saleId)) || (orderId && orderByTikTokId.get(orderId)) || (external && orderByTikTokId.get(external)) || null;
      return saleOrder ? { ...row, saleOrder } : null;
    })
    .filter(Boolean);

  const productStats = Array.from(confirmedRows.reduce((acc, row) => {
    const product = String(row.first_product_name || row.product_name || row.notes || 'Unknown product').trim() || 'Unknown product';
    const current = acc.get(product) || { product, orders: 0, revenue: 0, cogs: 0, fees: 0, profit: 0, buyers: new Set(), lots: new Set() };
    current.orders += 1;
    current.revenue += orderAmount(row);
    current.cogs += orderCOGS(row);
    current.fees += orderFees(row);
    current.profit += orderNetProfit(row);
    const buyer = orderBuyer(row);
    if (buyer) current.buyers.add(buyer);
    extractOrderLotValues(row).forEach((lot) => current.lots.add(lot));
    acc.set(product, current);
    return acc;
  }, new Map()).values())
    .map((item) => ({ ...item, buyers: item.buyers.size, lots: item.lots.size, margin: item.revenue ? (item.profit / item.revenue) * 100 : 0 }))
    .sort((a, b) => b.revenue - a.revenue);

  const buyerStats = Array.from(confirmedRows.reduce((acc, row) => {
    const buyer = orderBuyer(row) || row.partner_id_name || 'Unknown buyer';
    const current = acc.get(buyer) || {
      buyer,
      orders: 0,
      revenue: 0,
      profit: 0,
      products: new Set(),
      productMix: new Map(),
      regions: new Map(),
      first: null,
      latest: null,
      orderValues: [],
    };
    const amount = orderAmount(row);
    current.orders += 1;
    current.revenue += amount;
    current.profit += orderNetProfit(row);
    current.orderValues.push(amount);
    if (row.first_product_name) {
      current.products.add(row.first_product_name);
      current.productMix.set(row.first_product_name, (current.productMix.get(row.first_product_name) || 0) + 1);
    }
    const region = rowRegion(row);
    if (region) current.regions.set(region, (current.regions.get(region) || 0) + 1);
    const dt = dateValue(row);
    if (dt && (!current.first || dt < current.first)) current.first = dt;
    if (dt && (!current.latest || dt > current.latest)) current.latest = dt;
    acc.set(buyer, current);
    return acc;
  }, new Map()).values())
    .map((item) => {
      const avgOrder = item.orders ? item.revenue / item.orders : 0;
      const daysSinceLast = item.latest ? Math.max(0, Math.floor((Date.now() - item.latest.getTime()) / 86400000)) : null;
      const productMix = Array.from(item.productMix.entries())
        .map(([product, count]) => ({ product, count }))
        .sort((a, b) => b.count - a.count);
      const regions = Array.from(item.regions.entries()).sort((a, b) => b[1] - a[1]);
      const segment = item.revenue >= 150 && item.orders > 1
        ? 'VIP repeat'
        : item.orders > 1 && (daysSinceLast == null || daysSinceLast <= 14)
          ? 'Hot repeat'
          : item.orders === 1 && avgOrder >= aov
            ? 'High-AOV new'
            : item.orders > 1
              ? 'Repeat nurture'
              : 'One-time';
      const score = (item.revenue * 0.45) + (item.orders * 18) + (avgOrder * 0.8) - (daysSinceLast == null ? 0 : Math.min(daysSinceLast, 90) * 0.6);
      return {
        ...item,
        avgOrder,
        daysSinceLast,
        productList: Array.from(item.products),
        productMix,
        products: item.products.size,
        primaryRegion: regions[0]?.[0] || 'Unknown',
        segment,
        score,
      };
    })
    .sort((a, b) => b.revenue - a.revenue);

  const repeatBuyers = buyerStats.filter((buyer) => buyer.orders > 1);
  const vipBuyers = buyerStats.filter((buyer) => buyer.revenue >= 100).length;
  const oneTimeBuyers = buyerStats.filter((buyer) => buyer.orders === 1).length;
  const customerSegments = Array.from(buyerStats.reduce((acc, buyer) => {
    const current = acc.get(buyer.segment) || { segment: buyer.segment, buyers: 0, orders: 0, revenue: 0 };
    current.buyers += 1;
    current.orders += buyer.orders;
    current.revenue += buyer.revenue;
    acc.set(buyer.segment, current);
    return acc;
  }, new Map()).values()).sort((a, b) => b.revenue - a.revenue);
  const targetBuyers = buyerStats
    .slice()
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);
  const productAffinity = Array.from(confirmedRows.reduce((acc, row) => {
    const buyer = orderBuyer(row) || row.partner_id_name || 'Unknown buyer';
    const product = String(row.first_product_name || row.product_name || '').trim();
    if (!buyer || !product) return acc;
    const key = `${buyer}||${product}`;
    const current = acc.get(key) || { buyer, product, orders: 0, revenue: 0 };
    current.orders += 1;
    current.revenue += orderAmount(row);
    acc.set(key, current);
    return acc;
  }, new Map()).values())
    .sort((a, b) => b.orders - a.orders || b.revenue - a.revenue)
    .slice(0, 12);
  const buyerConcentration = revenue ? buyerStats.slice(0, 10).reduce((sum, buyer) => sum + buyer.revenue, 0) / revenue : 0;
  const regionStats = Array.from(confirmedRows.reduce((acc, row) => {
    const region = rowRegion(row);
    if (!region) return acc;
    const current = acc.get(region) || { region, orders: 0, revenue: 0, buyers: new Set(), productMix: new Map() };
    current.orders += 1;
    current.revenue += orderAmount(row);
    const buyer = orderBuyer(row);
    const product = String(row.first_product_name || row.product_name || '').trim();
    if (buyer) current.buyers.add(buyer);
    if (product) current.productMix.set(product, (current.productMix.get(product) || 0) + 1);
    acc.set(region, current);
    return acc;
  }, new Map()).values())
    .map((item) => {
      const topRegionProduct = Array.from(item.productMix.entries()).sort((a, b) => b[1] - a[1])[0];
      return {
        ...item,
        buyers: item.buyers.size,
        aov: item.orders ? item.revenue / item.orders : 0,
        topProduct: topRegionProduct?.[0] || 'Unknown product',
      };
    })
    .sort((a, b) => b.revenue - a.revenue);

  const recentTrend = Array.from(confirmedRows.reduce((acc, row) => {
    const dt = getSafeDate(row.date_order || row.ordered_at || row.created_at);
    if (!dt) return acc;
    const key = dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    const current = acc.get(key) || { day: key, revenue: 0, cogs: 0, profit: 0, fees: 0, orders: 0 };
    current.revenue += orderAmount(row);
    current.cogs += orderCOGS(row);
    current.fees += orderFees(row);
    current.profit += orderNetProfit(row);
    current.orders += 1;
    acc.set(key, current);
    return acc;
  }, new Map()).values()).slice(-10);

  const monthlyStats = Array.from(confirmedRows.reduce((acc, row) => {
    const dt = getSafeDate(row.date_order || row.ordered_at || row.created_at);
    if (!dt) return acc;
    const key = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}`;
    const label = dt.toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
    const current = acc.get(key) || { key, month: label, revenue: 0, cogs: 0, profit: 0, fees: 0, orders: 0, buyers: new Set() };
    current.revenue += orderAmount(row);
    current.cogs += orderCOGS(row);
    current.fees += orderFees(row);
    current.profit += orderNetProfit(row);
    current.orders += 1;
    const buyer = orderBuyer(row);
    if (buyer) current.buyers.add(buyer);
    acc.set(key, current);
    return acc;
  }, new Map()).values())
    .map((item) => ({ ...item, buyers: item.buyers.size, aov: item.orders ? item.revenue / item.orders : 0, margin: item.revenue ? (item.profit / item.revenue) * 100 : 0 }))
    .sort((a, b) => a.key.localeCompare(b.key));

  const inventoryRows = inventory?.rows || [];
  const soldNames = new Set(productStats.map((item) => item.product.toLowerCase()));
  const deadStock = inventoryRows
    .filter((item) => numberValue(item.on_hand_qty ?? item.qty_available ?? item.quantity) > 0)
    .filter((item) => !soldNames.has(String(item.name || item.product_name || '').toLowerCase()))
    .sort((a, b) => numberValue(b.on_hand_qty ?? b.qty_available ?? b.quantity) - numberValue(a.on_hand_qty ?? a.qty_available ?? a.quantity))
    .slice(0, 6);

  const inventoryByName = new Map(inventoryRows.map((item) => [String(item.name || item.product_name || '').trim().toLowerCase(), item]));
  const reorderCandidates = productStats
    .map((item) => {
      const stock = inventoryByName.get(item.product.toLowerCase());
      const onHand = numberValue(stock?.on_hand_qty ?? stock?.qty_available ?? stock?.quantity);
      return { ...item, onHand };
    })
    .filter((item) => item.orders >= 2 && item.profit > 0)
    .sort((a, b) => (a.onHand - b.onHand) || (b.profit - a.profit))
    .slice(0, 8);

  const lotRangeStats = Array.from(confirmedRows.reduce((acc, row) => {
    const lots = extractOrderLotValues(row);
    const lotNumber = Number(lots[0] || 0);
    const range = lotNumber >= 301 && lotNumber <= 364
      ? 'Batch 2 (301-364)'
      : lotNumber >= 1 && lotNumber <= 300
        ? 'Batch 1 (1-300)'
        : lotNumber
          ? 'Other lots'
          : 'No lot';
    const current = acc.get(range) || { range, orders: 0, revenue: 0, cogs: 0, fees: 0, profit: 0, lots: new Set() };
    current.orders += 1;
    current.revenue += orderAmount(row);
    current.cogs += orderCOGS(row);
    current.fees += orderFees(row);
    current.profit += orderNetProfit(row);
    lots.forEach((lot) => current.lots.add(lot));
    acc.set(range, current);
    return acc;
  }, new Map()).values())
    .map((item) => ({ ...item, lots: item.lots.size, margin: item.revenue ? (item.profit / item.revenue) * 100 : 0 }))
    .sort((a, b) => b.revenue - a.revenue);

  const lowProfitLots = confirmedRows
    .map((row) => ({
      row,
      lot: extractOrderLotValues(row)[0] || 'No lot',
      product: row.first_product_name || row.product_name || 'Unknown product',
      buyer: orderBuyer(row) || 'Unknown buyer',
      revenue: orderAmount(row),
      profit: orderNetProfit(row),
    }))
    .filter((item) => item.profit <= 0 || (item.revenue > 0 && (item.profit / item.revenue) < 0.1))
    .sort((a, b) => a.profit - b.profit)
    .slice(0, 12);

  const packingGroups = Array.from(confirmedRows.reduce((acc, row) => {
    const tracking = orderTracking(row) || row.order_number || row.name || `order-${row.id}`;
    const current = acc.get(tracking) || { tracking, buyer: orderBuyer(row) || 'Unknown buyer', orders: 0, items: 0, lots: new Set(), revenue: 0, products: new Set() };
    current.orders += 1;
    current.items += numberValue(row.qty || row.quantity || row.product_uom_qty || 1) || 1;
    current.revenue += orderAmount(row);
    const product = row.first_product_name || row.product_name;
    if (product) current.products.add(product);
    extractOrderLotValues(row).forEach((lot) => current.lots.add(lot));
    acc.set(tracking, current);
    return acc;
  }, new Map()).values())
    .map((item) => ({ ...item, lots: item.lots.size, products: Array.from(item.products) }))
    .filter((item) => item.orders > 1 || item.lots > 1 || item.items > 1)
    .sort((a, b) => b.lots - a.lots || b.revenue - a.revenue)
    .slice(0, 10);

  const returnRiskProducts = Array.from(matchedReturnRows.reduce((acc, item) => {
    const saleOrder = item.saleOrder || {};
    const product = String(saleOrder.first_product_name || saleOrder.product_name || 'Unknown product').trim();
    const current = acc.get(product) || { product, returns: 0, refund: 0, buyers: new Set() };
    current.returns += 1;
    current.refund += numberValue(item.total_refund_amount || item.refund_amount);
    const buyer = orderBuyer(saleOrder) || item.whatnot_buyer_username;
    if (buyer) current.buyers.add(buyer);
    acc.set(product, current);
    return acc;
  }, new Map()).values())
    .map((item) => ({ ...item, buyers: item.buyers.size }))
    .sort((a, b) => b.returns - a.returns || b.refund - a.refund);

  const returnRiskCustomers = Array.from(matchedReturnRows.reduce((acc, item) => {
    const saleOrder = item.saleOrder || {};
    const buyer = orderBuyer(saleOrder) || item.whatnot_buyer_username || 'Unknown buyer';
    const current = acc.get(buyer) || { buyer, returns: 0, refund: 0 };
    current.returns += 1;
    current.refund += numberValue(item.total_refund_amount || item.refund_amount);
    acc.set(buyer, current);
    return acc;
  }, new Map()).values()).sort((a, b) => b.returns - a.returns || b.refund - a.refund);

  const sessionCostTrend = Array.from(confirmedRows.reduce((acc, row) => {
    const sessionKey = row.session_id || row.live_session_id || row.tiktok_live_session_id || 'No session';
    const label = sessionKey === 'No session' ? sessionKey : `Session ${sessionKey}`;
    const current = acc.get(String(sessionKey)) || { session: label, revenue: 0, cogs: 0, fees: 0, profit: 0, orders: 0 };
    current.revenue += orderAmount(row);
    current.cogs += orderCOGS(row);
    current.fees += orderFees(row);
    current.profit += orderNetProfit(row);
    current.orders += 1;
    acc.set(String(sessionKey), current);
    return acc;
  }, new Map()).values()).sort((a, b) => b.revenue - a.revenue);

  const ordersToShip = confirmedRows.filter((row) => !['shipped', 'delivered'].includes(String(row.fulfillment_status || '').toLowerCase())).length;
  const shippedOrders = confirmedRows.filter((row) => ['shipped', 'delivered'].includes(String(row.fulfillment_status || '').toLowerCase())).length;
  const fulfillmentSpeed = confirmedRows.length ? Math.round((shippedOrders / confirmedRows.length) * 100) : 0;
  const totalAuctionRows = rows.length;
  const cancelledRate = totalAuctionRows ? (cancelledRows.length / totalAuctionRows) * 100 : 0;
  const missingLotRows = confirmedRows.filter((row) => !extractOrderLotValues(row).length).length;
  const missingLotRate = confirmedRows.length ? (missingLotRows / confirmedRows.length) * 100 : 0;
  const recentOrders = confirmedRows
    .slice()
    .sort((a, b) => (getSafeDate(b.date_order || b.ordered_at || b.created_at)?.getTime() || 0) - (getSafeDate(a.date_order || a.ordered_at || a.created_at)?.getTime() || 0))
    .slice(0, 10);
  const trackedSessionMinutes = (sessions || []).reduce((sum, session) => {
    const start = getSafeDate(session.started_at);
    const end = getSafeDate(session.ended_at) || new Date();
    if (!start || !end || end <= start) return sum;
    return sum + ((end.getTime() - start.getTime()) / 60000);
  }, 0);
  const revenuePerMinute = revenue / Math.max(1, trackedSessionMinutes);
  const ordersPerMinute = confirmedRows.length / Math.max(1, trackedSessionMinutes);

  const topProduct = productStats[0];
  const topBuyer = buyerStats[0];
  const topBuyerShare = revenue && topBuyer ? topBuyer.revenue / revenue : 0;
  const bestRegion = regionStats[0];
  const selectedBuyerStats = selectedBuyer ? buyerStats.find((buyer) => buyer.buyer === selectedBuyer) : null;
  const selectedBuyerOrders = selectedBuyer
    ? confirmedRows
      .filter((row) => (orderBuyer(row) || row.partner_id_name || 'Unknown buyer') === selectedBuyer)
      .slice()
      .sort((a, b) => (dateValue(b)?.getTime() || 0) - (dateValue(a)?.getTime() || 0))
    : [];
  const bestMonth = monthlyStats.slice().sort((a, b) => b.revenue - a.revenue)[0];
  const trendProduct = productStats.find((item) => item.orders >= 3) || topProduct;
  const bundleCandidates = productStats.slice(0, 3).map((item) => item.product);
  const lowVelocityProduct = deadStock[0];
  const nextLiveWindow = recentTrend.length >= 2
    ? `${recentTrend[recentTrend.length - 1].day} style products are moving now`
    : 'Use the next upload to learn your best live window';

  const insightCards = [
    {
      title: 'What to sell next',
      value: trendProduct ? trendProduct.product : 'Need more TikTok sales',
      detail: trendProduct ? `${trendProduct.orders} orders · ${money(trendProduct.revenue)} revenue` : 'Import more orders to rank products.',
    },
    {
      title: 'Who to target',
      value: topBuyer ? topBuyer.buyer : 'No buyer signal yet',
      detail: topBuyer ? `${topBuyer.orders} orders · ${money(topBuyer.revenue)} revenue` : 'Buyer segments appear after TikTok Live auction sales.',
    },
    {
      title: 'When to go live',
      value: nextLiveWindow,
      detail: `${activeSessions} live now · ${sessions.length} TikTok sessions tracked`,
    },
    {
      title: 'What to bundle',
      value: bundleCandidates.length ? bundleCandidates.join(' + ') : 'Need product history',
      detail: bundleCandidates.length ? 'Bundle top movers with slow-moving inventory.' : 'Top product pairings need more line history.',
    },
    {
      title: 'How to pack faster',
      value: `${ordersToShip} orders to ship`,
      detail: `${fulfillmentSpeed}% already shipped/delivered. Batch by buyer and top product first.`,
    },
  ];

  const decisionPanelStyle = {
    border: '1px solid rgba(148,163,184,0.22)',
    borderRadius: 24,
    background: 'rgba(255,255,255,0.92)',
    boxShadow: '0 18px 50px rgba(15,23,42,0.07)',
    padding: 18,
    minWidth: 0,
  };

  const sectionTitle = (eyebrow, title, sub) => (
    <div style={{ display: 'grid', gap: 5, marginBottom: 14 }}>
      <div style={{ fontSize: 11, fontWeight: 900, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#64748b' }}>{eyebrow}</div>
      <div style={{ fontSize: 20, fontWeight: 950, color: '#0f172a', letterSpacing: '-0.04em' }}>{title}</div>
      {sub ? <div style={{ fontSize: 13, color: '#64748b' }}>{sub}</div> : null}
    </div>
  );

  const listRow = (left, right, sub, options = {}) => (
    <div
      key={`${left}-${right}`}
      role={options.onClick ? 'button' : undefined}
      tabIndex={options.onClick ? 0 : undefined}
      onClick={options.onClick}
      onKeyDown={(event) => {
        if (!options.onClick) return;
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          options.onClick();
        }
      }}
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        gap: 12,
        padding: '10px 8px',
        borderTop: '1px solid rgba(226,232,240,0.85)',
        borderRadius: options.active ? 12 : 0,
        background: options.active ? 'rgba(109,93,252,0.08)' : 'transparent',
        cursor: options.onClick ? 'pointer' : 'default',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 850, color: '#0f172a', overflow: 'hidden', textOverflow: 'ellipsis' }}>{left}</div>
        {sub ? <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>{sub}</div> : null}
      </div>
      <div style={{ fontSize: 13, fontWeight: 900, color: '#0f766e', whiteSpace: 'nowrap' }}>{right}</div>
    </div>
  );

  function exportDecisionCsv() {
    const escapeCsv = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;
    const lines = [
      ['Section', 'Metric', 'Value', 'Detail'],
      ['Overview', 'Orders', confirmedRows.length, `${cancelledRows.length} cancelled, ${unconfirmedRows.length} unconfirmed`],
      ['Overview', 'Revenue', revenue.toFixed(2), 'Confirmed TikTok revenue'],
      ['Overview', 'COGS', totalCogs.toFixed(2), 'Estimated cost of goods sold'],
      ['Overview', 'Fees', totalFees.toFixed(2), 'TikTok platform fees at 6% when no explicit fee exists'],
      ['Overview', 'Net Profit', netProfit.toFixed(2), `${netMarginPct.toFixed(1)}% net margin after fees`],
      ['Overview', 'AOV', aov.toFixed(2), 'Average paid order'],
      ['Overview', 'Orders to ship', ordersToShip, `${fulfillmentSpeed}% shipped/delivered`],
      ['Quality', 'Returns', matchedReturnRows.length, `${returnSummary.total || returnRows.length || 0} TikTok return rows pulled`],
      ['Quality', 'Cancelled Rate', cancelledRate.toFixed(1), `${cancelledRows.length} cancelled of ${totalAuctionRows} TikTok Live auction orders`],
      ['Quality', 'Missing Lot Rate', missingLotRate.toFixed(1), `${missingLotRows} confirmed rows without a lot number`],
      ...insightCards.map((card) => ['Decision', card.title, card.value, card.detail]),
      ...productStats.slice(0, 25).map((item) => ['Products', item.product, item.revenue.toFixed(2), `${item.orders} orders, ${item.buyers} buyers, profit ${item.profit.toFixed(2)}, margin ${item.margin.toFixed(1)}%`]),
      ...lotRangeStats.map((item) => ['Lot Ranges', item.range, item.revenue.toFixed(2), `${item.orders} orders, COGS ${item.cogs.toFixed(2)}, profit ${item.profit.toFixed(2)}, margin ${item.margin.toFixed(1)}%`]),
      ...buyerStats.slice(0, 25).map((item) => ['Customers', item.buyer, item.revenue.toFixed(2), `${item.segment}, ${item.orders} orders, profit ${item.profit.toFixed(2)}, AOV ${item.avgOrder.toFixed(2)}, ${item.products} products`]),
      ...packingGroups.map((item) => ['Packing', item.tracking, item.revenue.toFixed(2), `${item.buyer}, ${item.lots} lots, ${item.orders} rows`]),
      ...lowProfitLots.map((item) => ['Low Profit Lots', item.lot, item.profit.toFixed(2), `${item.product}, ${item.buyer}, revenue ${item.revenue.toFixed(2)}`]),
      ...returnRiskProducts.map((item) => ['Return Risk Products', item.product, item.returns, `${item.buyers} buyers, refund ${item.refund.toFixed(2)}`]),
      ...returnRiskCustomers.map((item) => ['Return Risk Customers', item.buyer, item.returns, `refund ${item.refund.toFixed(2)}`]),
      ...customerSegments.map((item) => ['Customer Segments', item.segment, item.revenue.toFixed(2), `${item.buyers} buyers, ${item.orders} orders`]),
      ...productAffinity.map((item) => ['Product Affinity', item.buyer, item.product, `${item.orders} orders, ${item.revenue.toFixed(2)} revenue`]),
      ...regionStats.slice(0, 25).map((item) => ['Regions', item.region, item.revenue.toFixed(2), `${item.orders} orders, ${item.buyers} buyers, AOV ${item.aov.toFixed(2)}, top product ${item.topProduct}`]),
      ...monthlyStats.slice(-24).map((item) => ['Monthly', item.month, item.revenue.toFixed(2), `${item.orders} orders, COGS ${item.cogs.toFixed(2)}, profit ${item.profit.toFixed(2)}, margin ${item.margin.toFixed(1)}%`]),
    ].map((row) => row.map(escapeCsv).join(',')).join('\n');
    const blob = new Blob([lines], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `tiktok-decision-engine-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  const analysisTabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'orders', label: 'Orders' },
    { id: 'products', label: 'Products' },
    { id: 'profit', label: 'Profit' },
    { id: 'operations', label: 'Packing' },
    { id: 'customers', label: 'Customers' },
    { id: 'returns', label: 'Returns' },
    { id: 'monthly', label: 'Monthly' },
  ];

  return (
    <div
      style={{
        display: 'grid',
        gap: 16,
        padding: 14,
        borderRadius: 28,
        background: 'linear-gradient(180deg, #f8fafc 0%, #f3f4f8 100%)',
        border: '1px solid rgba(226,232,240,0.9)',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 12,
          padding: '10px 12px',
          borderRadius: 20,
          background: '#ffffff',
          border: '1px solid rgba(226,232,240,0.95)',
          boxShadow: '0 10px 26px rgba(15,23,42,0.045)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 36, height: 36, borderRadius: 14, background: 'linear-gradient(135deg, #6d5dfc, #8b5cf6)', color: '#fff', display: 'grid', placeItems: 'center', fontWeight: 950 }}>D</div>
          <div>
            <div style={{ fontSize: 18, fontWeight: 950, color: '#111827', letterSpacing: '-0.04em' }}>Dashboard</div>
            <div style={{ fontSize: 12, color: '#6b7280' }}>TikTok analytics and decision support</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          {analysisTabs.map((item) => (
            <button
              key={item.label}
              type="button"
              onClick={() => setAnalysisMode(item.id)}
              style={{
                border: '1px solid rgba(226,232,240,0.95)',
                background: analysisMode === item.id ? '#111827' : '#fff',
                color: analysisMode === item.id ? '#fff' : '#374151',
                borderRadius: 12,
                padding: '8px 11px',
                fontSize: 12,
                fontWeight: 850,
                cursor: 'pointer',
              }}
            >
              {item.label}
            </button>
          ))}
          <button type="button" onClick={exportDecisionCsv} style={{ border: 'none', background: '#6d5dfc', color: '#fff', borderRadius: 12, padding: '9px 13px', fontSize: 12, fontWeight: 900, boxShadow: '0 10px 18px rgba(109,93,252,0.22)', cursor: 'pointer' }}>Export</button>
        </div>
      </div>

      <section
        style={{
          borderRadius: 26,
          padding: 20,
          overflow: 'hidden',
          color: '#111827',
          background: '#ffffff',
          border: '1px solid rgba(226,232,240,0.95)',
          boxShadow: '0 18px 46px rgba(15,23,42,0.06)',
        }}
      >
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(280px, 0.8fr)', gap: 18, alignItems: 'stretch' }}>
          <div style={{ display: 'grid', gap: 14 }}>
            <div style={{ display: 'inline-flex', width: 'fit-content', padding: '7px 11px', borderRadius: 999, background: '#f3f0ff', border: '1px solid rgba(109,93,252,0.16)', color: '#6d5dfc', fontSize: 11, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase' }}>
              TikTok Decision Engine
            </div>
            <div style={{ fontSize: 34, fontWeight: 950, letterSpacing: '-0.06em', lineHeight: 1, color: '#111827' }}>
              Not reports. Decisions.
            </div>
            <div style={{ maxWidth: 760, color: '#64748b', fontSize: 14, lineHeight: 1.7 }}>
              This view uses TikTok Live auction orders only: total auction orders, cancelled orders, returns, COGS, fees, net margin, product profit, batch performance, and packing risk.
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10, marginTop: 8 }}>
              <DecisionStat light label="Confirmed" value={confirmedRows.length.toLocaleString()} sub="TikTok auction orders" />
              <DecisionStat light label="Cancelled" value={cancelledRows.length.toLocaleString()} sub={`${cancelledRate.toFixed(1)}% cancel rate`} />
              <DecisionStat light label="Returns" value={matchedReturnRows.length.toLocaleString()} sub={`${returnSummary.total || returnRows.length || 0} pulled`} />
              <DecisionStat light label="Revenue" value={money(revenue)} sub="TikTok Live only" />
              <DecisionStat light label="COGS" value={money(totalCogs)} sub="cost of goods" />
              <DecisionStat light label="Net Margin" value={`${netMarginPct.toFixed(1)}%`} sub={`${money(netProfit)} after fees`} />
              <DecisionStat light label="Live Activity" value={String(activeSessions)} sub={`${sessions.length} sessions tracked`} />
            </div>
          </div>
          <div style={{ borderRadius: 24, background: 'linear-gradient(180deg, #f8fafc, #ffffff)', border: '1px solid rgba(226,232,240,0.95)', padding: 16, display: 'grid', gap: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 950, color: '#111827' }}>Final insight</div>
            {insightCards.slice(0, 3).map((item) => (
              <div key={item.title} style={{ padding: 12, borderRadius: 18, background: '#ffffff', border: '1px solid rgba(226,232,240,0.9)', boxShadow: '0 8px 18px rgba(15,23,42,0.035)' }}>
                <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', fontWeight: 900, letterSpacing: '0.1em' }}>{item.title}</div>
                <div style={{ marginTop: 5, fontSize: 14, fontWeight: 900, color: '#111827' }}>{item.value}</div>
                <div style={{ marginTop: 3, fontSize: 12, color: '#64748b' }}>{item.detail}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {analysisMode === 'overview' ? (
        <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(180px, 1fr))', gap: 12 }}>
        {insightCards.map((card) => (
          <div key={card.title} style={{ ...decisionPanelStyle, padding: 16 }}>
            <div style={{ fontSize: 11, color: '#64748b', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.1em' }}>{card.title}</div>
            <div style={{ marginTop: 8, fontSize: 16, color: '#0f172a', fontWeight: 950, lineHeight: 1.25 }}>{card.value}</div>
            <div style={{ marginTop: 7, fontSize: 12, color: '#64748b', lineHeight: 1.5 }}>{card.detail}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 14 }}>
        <section id="tiktok-analysis-overview" style={decisionPanelStyle}>
          {sectionTitle('Overview', 'Revenue and order pulse', 'Live activity, order volume, revenue trend, and average order value.')}
          <div style={{ height: 260 }}>
            {recentTrend.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={recentTrend}>
                  <defs>
                    <linearGradient id="tiktokRevenueGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#14b8a6" stopOpacity={0.38} />
                      <stop offset="95%" stopColor="#14b8a6" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.22)" />
                  <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 11 }} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                  <Tooltip formatter={(value, name) => [name === 'orders' ? value : money(value), name]} />
                  <Area type="monotone" dataKey="revenue" stroke="#0f766e" fill="url(#tiktokRevenueGradient)" strokeWidth={3} />
                  <Line type="monotone" dataKey="orders" stroke="#f59e0b" strokeWidth={2} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <EmptyInsight title="No trend yet" text="Import TikTok orders with dates to unlock revenue and order trend charts." />
            )}
          </div>
        </section>

        <section id="tiktok-analysis-live" style={decisionPanelStyle}>
          {sectionTitle('Live Analytics', 'Real-time selling signals', 'Revenue/min, orders/min, and session velocity.')}
          <div style={{ display: 'grid', gap: 10 }}>
            <DecisionStat light label="Revenue / min" value={money(revenuePerMinute)} sub="across tracked sessions" />
            <DecisionStat light label="Orders / min" value={ordersPerMinute.toFixed(2)} sub="confirmed TikTok pace" />
            <DecisionStat light label="Best live prompt" value={topProduct?.product || 'No product yet'} sub="start with your highest-confidence item" />
          </div>
        </section>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(240px, 1fr))', gap: 14 }}>
        <section id="tiktok-analysis-products" style={decisionPanelStyle}>
          {sectionTitle('Products', 'Top selling and trending', 'Use this to plan the next rack and bundle strategy.')}
          {productStats.slice(0, 7).map((item) => listRow(item.product, money(item.revenue), `${item.orders} orders · ${item.buyers} buyers`))}
          {!productStats.length ? <EmptyInsight title="No product sales yet" text="Confirmed orders need product names before this can rank products." /> : null}
        </section>

        <section id="tiktok-analysis-customers" style={decisionPanelStyle}>
          {sectionTitle('Customers', 'Top and repeat buyers', 'Target repeat buyers first, then segment by products bought.')}
          {buyerStats.slice(0, 7).map((item) => listRow(item.buyer, money(item.revenue), `${item.orders} orders · ${item.products} products`))}
          {!buyerStats.length ? <EmptyInsight title="No buyer signal yet" text="Confirmed TikTok sales will populate top buyers and repeat buyer segments." /> : null}
        </section>

        <section id="tiktok-analysis-regions" style={decisionPanelStyle}>
          {sectionTitle('Regions', 'State performance', 'Map view placeholder plus ranked state performance.')}
          <div style={{ height: 132, borderRadius: 20, background: 'linear-gradient(135deg, rgba(15,118,110,0.13), rgba(245,158,11,0.1)), repeating-linear-gradient(45deg, rgba(148,163,184,0.18) 0, rgba(148,163,184,0.18) 1px, transparent 1px, transparent 14px)', border: '1px solid rgba(148,163,184,0.22)', display: 'grid', placeItems: 'center', color: '#64748b', fontWeight: 850 }}>
            Map view ready for shipping-state data
          </div>
          <div style={{ marginTop: 10 }}>
            {regionStats.slice(0, 5).map((item) => listRow(item.region, money(item.revenue), `${item.orders} orders`))}
            {!regionStats.length ? <div style={{ fontSize: 12, color: '#64748b', marginTop: 10 }}>No state data found yet in customers/orders.</div> : null}
          </div>
        </section>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '0.9fr 1.1fr', gap: 14 }}>
        <section id="tiktok-analysis-operations" style={decisionPanelStyle}>
          {sectionTitle('Operations', 'Ship faster', 'Orders to ship, batching, and fulfillment speed.')}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
            <DecisionStat light label="Orders to ship" value={ordersToShip.toLocaleString()} sub="paid but not shipped" />
            <DecisionStat light label="Fulfillment speed" value={`${fulfillmentSpeed}%`} sub="shipped / confirmed" />
            <DecisionStat light label="Batch idea" value={topProduct ? topProduct.orders : 0} sub={topProduct ? `pull ${topProduct.product} first` : 'needs product data'} />
          </div>
        </section>

        <section style={decisionPanelStyle}>
          {sectionTitle('Dead Stock', 'Inventory needing attention', 'Products with stock but no TikTok demand signal in this dataset.')}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8 }}>
            {deadStock.slice(0, 6).map((item) => (
              <div key={`${item.id || item.barcode || item.name}`} style={{ padding: 12, borderRadius: 16, background: 'rgba(248,250,252,0.95)', border: '1px solid rgba(226,232,240,0.9)' }}>
                <div style={{ fontSize: 13, fontWeight: 900, color: '#0f172a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.name || item.product_name || 'Unnamed product'}</div>
                <div style={{ marginTop: 5, fontSize: 12, color: '#64748b' }}>{numberValue(item.on_hand_qty ?? item.qty_available ?? item.quantity)} on hand · try bundle with {topProduct?.product || 'a top mover'}</div>
              </div>
            ))}
            {!deadStock.length ? <EmptyInsight title="No dead stock signal" text="Inventory names and TikTok product history are needed to spot slow movers." /> : null}
          </div>
        </section>
      </div>
        </>
      ) : null}

      {analysisMode === 'orders' ? (
        <div style={{ display: 'grid', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(160px, 1fr))', gap: 12 }}>
            <DecisionStat light label="Confirmed orders" value={confirmedRows.length.toLocaleString()} sub="all TikTok auction orders" />
            <DecisionStat light label="Cancelled" value={cancelledRows.length.toLocaleString()} sub={`${cancelledRate.toFixed(1)}% cancel rate`} />
            <DecisionStat light label="Orders to ship" value={ordersToShip.toLocaleString()} sub={`${fulfillmentSpeed}% fulfilled`} />
            <DecisionStat light label="Average order" value={money(aov)} sub="TikTok auction order" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1.15fr 0.85fr', gap: 14 }}>
            <section style={decisionPanelStyle}>
              {sectionTitle('Orders', 'Order volume and revenue', 'Dedicated order analysis for pace, revenue, and fulfillment load.')}
              <div style={{ height: 290 }}>
                {recentTrend.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={recentTrend}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.22)" />
                      <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 11 }} />
                      <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
                      <Tooltip formatter={(value, name) => [name === 'revenue' ? money(value) : value, name]} />
                      <Bar dataKey="orders" fill="#6d5dfc" radius={[8, 8, 0, 0]} />
                      <Bar dataKey="revenue" fill="#14b8a6" radius={[8, 8, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyInsight title="No order trend yet" text="Confirmed TikTok orders with dates are needed." />
                )}
              </div>
            </section>

            <section style={decisionPanelStyle}>
              {sectionTitle('Operations', 'Recent confirmed orders', 'Use this to spot newest packing pressure fast.')}
              {recentOrders.map((row) => listRow(row.order_number || row.name || `Order ${row.id}`, money(orderAmount(row)), `${orderBuyer(row) || 'Unknown buyer'} · ${row.fulfillment_status || 'pending'}`))}
              {!recentOrders.length ? <EmptyInsight title="No recent orders" text="Confirmed orders will appear here." /> : null}
            </section>
          </div>
        </div>
      ) : null}

      {analysisMode === 'products' ? (
        <div style={{ display: 'grid', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(160px, 1fr))', gap: 12 }}>
            <DecisionStat light label="Products sold" value={productStats.length.toLocaleString()} sub="Unique products" />
            <DecisionStat light label="Top product" value={topProduct ? `${topProduct.orders}` : '0'} sub={topProduct?.product || 'No product yet'} />
            <DecisionStat light label="Dead stock watch" value={deadStock.length.toLocaleString()} sub="Stock with no TikTok signal" />
            <DecisionStat light label="Bundle candidates" value={bundleCandidates.length.toLocaleString()} sub="Top movers ready" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <section style={decisionPanelStyle}>
              {sectionTitle('Products', 'Top selling products', 'Ranked by confirmed TikTok revenue.')}
              <div style={{ height: 310 }}>
                {productStats.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={productStats.slice(0, 10)} layout="vertical" margin={{ left: 16, right: 16 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
                      <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                      <YAxis type="category" dataKey="product" width={150} tick={{ fill: '#64748b', fontSize: 11 }} />
                      <Tooltip formatter={(value, name) => [name === 'revenue' ? money(value) : value, name]} />
                      <Bar dataKey="revenue" fill="#14b8a6" radius={[0, 8, 8, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyInsight title="No product sales yet" text="Import confirmed orders with product names to rank top sellers." />
                )}
              </div>
            </section>

            <section style={decisionPanelStyle}>
              {sectionTitle('Product Strategy', 'Trending, bundle, and dead stock', 'What to sell next and what to pair it with.')}
              {productStats.slice(0, 6).map((item) => listRow(item.product, money(item.revenue), `${item.orders} orders · ${item.buyers} buyers`))}
              <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid rgba(226,232,240,0.9)' }}>
                <div style={{ fontSize: 12, fontWeight: 950, color: '#0f172a', marginBottom: 8 }}>Bundle idea</div>
                <div style={{ fontSize: 13, color: '#64748b', lineHeight: 1.5 }}>
                  {bundleCandidates.length ? `${bundleCandidates.join(' + ')}${lowVelocityProduct ? ` + ${lowVelocityProduct.name || lowVelocityProduct.product_name}` : ''}` : 'Need more sold product history to recommend bundles.'}
                </div>
              </div>
            </section>
          </div>
        </div>
      ) : null}

      {analysisMode === 'profit' ? (
        <div style={{ display: 'grid', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(140px, 1fr))', gap: 12 }}>
            <DecisionStat light label="Revenue" value={money(revenue)} sub="TikTok Live only" />
            <DecisionStat light label="COGS" value={money(totalCogs)} sub="product cost" />
            <DecisionStat light label="Fees 6%" value={money(totalFees)} sub="TikTok platform fee" />
            <DecisionStat light label="Net profit" value={money(netProfit)} sub="after fees" />
            <DecisionStat light label="Net margin" value={`${netMarginPct.toFixed(1)}%`} sub="profit / revenue" />
            <DecisionStat light label="Loss watch" value={lowProfitLots.length.toLocaleString()} sub="low-profit lots" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <section style={decisionPanelStyle}>
              {sectionTitle('Product Profit', 'Profit by product', 'Revenue, cost, fees, net profit, and margin after TikTok fees.')}
              {productStats.slice(0, 12).map((item) => listRow(
                item.product,
                money(item.profit),
                `${item.orders} orders · revenue ${money(item.revenue)} · COGS ${money(item.cogs)} · fees ${money(item.fees)} · margin ${item.margin.toFixed(1)}%`,
              ))}
              {!productStats.length ? <EmptyInsight title="No product profit yet" text="TikTok Live orders need product and cost data for product profit." /> : null}
            </section>

            <section style={decisionPanelStyle}>
              {sectionTitle('Lot Ranges', 'Batch 1 vs Batch 2', 'Batch 1 is lots 1-300. Batch 2 is lots 301-364.')}
              {lotRangeStats.map((item) => listRow(
                item.range,
                money(item.profit),
                `${item.orders} orders · ${item.lots} lots · revenue ${money(item.revenue)} · COGS ${money(item.cogs)} · margin ${item.margin.toFixed(1)}%`,
              ))}
              {!lotRangeStats.length ? <EmptyInsight title="No lot range data" text="Lot numbers are needed to compare batch performance." /> : null}
            </section>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <section style={decisionPanelStyle}>
              {sectionTitle('Loss Control', 'Low-profit or loss lots', 'These lots need price, cost, or fee review before reordering.')}
              {lowProfitLots.map((item) => listRow(
                `Lot ${item.lot} · ${item.product}`,
                money(item.profit),
                `${item.buyer} · revenue ${money(item.revenue)} · margin ${item.revenue ? ((item.profit / item.revenue) * 100).toFixed(1) : '0.0'}%`,
              ))}
              {!lowProfitLots.length ? <EmptyInsight title="No low-profit lots" text="No TikTok Live lots are below the margin threshold." /> : null}
            </section>

            <section style={decisionPanelStyle}>
              {sectionTitle('Reorder Intelligence', 'Best products to reorder', 'Top movers with positive profit, sorted with low stock first when inventory matches.')}
              {reorderCandidates.map((item) => listRow(
                item.product,
                money(item.profit),
                `${item.orders} orders · ${item.onHand} on hand · revenue ${money(item.revenue)} · margin ${item.margin.toFixed(1)}%`,
              ))}
              {!reorderCandidates.length ? <EmptyInsight title="No reorder signal yet" text="Need profitable repeat product sales and matching inventory names." /> : null}
            </section>
          </div>
        </div>
      ) : null}

      {analysisMode === 'operations' ? (
        <div style={{ display: 'grid', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(150px, 1fr))', gap: 12 }}>
            <DecisionStat light label="Big packs" value={packingGroups.length.toLocaleString()} sub="multi-lot labels" />
            <DecisionStat light label="Orders to ship" value={ordersToShip.toLocaleString()} sub={`${fulfillmentSpeed}% fulfilled`} />
            <DecisionStat light label="Cancelled rate" value={`${cancelledRate.toFixed(1)}%`} sub={`${cancelledRows.length} cancelled`} />
            <DecisionStat light label="Missing lot rate" value={`${missingLotRate.toFixed(1)}%`} sub={`${missingLotRows} rows`} />
            <DecisionStat light label="AOV" value={money(aov)} sub="average auction order" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <section style={decisionPanelStyle}>
              {sectionTitle('Packing Risk', 'Big orders needing careful packing', 'Grouped by tracking number when available, then order number.')}
              {packingGroups.map((item) => listRow(
                item.tracking,
                `${item.lots} lots`,
                `${item.buyer} · ${item.orders} rows · ${money(item.revenue)} · ${item.products.slice(0, 2).join(' · ') || 'No product names'}`,
              ))}
              {!packingGroups.length ? <EmptyInsight title="No big packing groups" text="No multi-lot TikTok Live orders were found in this dataset." /> : null}
            </section>

            <section style={decisionPanelStyle}>
              {sectionTitle('Session Cost Trend', 'COGS vs revenue by session', 'Use this to compare session quality, not just total sales.')}
              {sessionCostTrend.slice(0, 12).map((item) => listRow(
                item.session,
                money(item.profit),
                `${item.orders} orders · revenue ${money(item.revenue)} · COGS ${money(item.cogs)} · fees ${money(item.fees)}`,
              ))}
              {!sessionCostTrend.length ? <EmptyInsight title="No session cost trend" text="Session IDs are needed on TikTok Live orders for session trend analysis." /> : null}
            </section>
          </div>
        </div>
      ) : null}

      {analysisMode === 'customers' ? (
        <div style={{ display: 'grid', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(140px, 1fr))', gap: 12 }}>
            <DecisionStat light label="Customers" value={buyerStats.length.toLocaleString()} sub="Unique buyers" />
            <DecisionStat light label="Repeat buyers" value={repeatBuyers.length.toLocaleString()} sub="2+ orders" />
            <DecisionStat light label="VIP buyers" value={vipBuyers.toLocaleString()} sub="$100+ paid" />
            <DecisionStat light label="One-time buyers" value={oneTimeBuyers.toLocaleString()} sub="Retarget list" />
            <DecisionStat light label="Top buyer share" value={`${(topBuyerShare * 100).toFixed(1)}%`} sub={topBuyer?.buyer || 'No buyer'} />
            <DecisionStat light label="Top 10 share" value={`${(buyerConcentration * 100).toFixed(1)}%`} sub="Revenue concentration" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <section style={decisionPanelStyle}>
              {sectionTitle('Customers', 'Who to target next', 'Ranked by spend, repeat behavior, AOV, and recency.')}
              {targetBuyers.slice(0, 12).map((item) => listRow(
                item.buyer,
                money(item.revenue),
                `${item.segment} · ${item.orders} orders · AOV ${money(item.avgOrder)} · ${item.primaryRegion}`,
                {
                  active: selectedBuyer === item.buyer,
                  onClick: () => setSelectedBuyer(item.buyer),
                },
              ))}
              {!buyerStats.length ? <EmptyInsight title="No customer data yet" text="Buyer names from imported orders will appear here." /> : null}
            </section>

            <section style={decisionPanelStyle}>
              {sectionTitle('Segments', 'Buyer quality and retention', 'VIP, repeat, new high-AOV, and one-time buyer split.')}
              <div style={{ height: 240 }}>
                {buyerStats.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={customerSegments.map((item) => ({ name: item.segment, value: item.buyers }))}
                        dataKey="value"
                        nameKey="name"
                        innerRadius={58}
                        outerRadius={88}
                        paddingAngle={4}
                      >
                        {['#6d5dfc', '#14b8a6', '#f59e0b', '#ef4444', '#3b82f6'].map((color) => <Cell key={color} fill={color} />)}
                      </Pie>
                      <Tooltip />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyInsight title="No segments yet" text="Customer segments unlock once confirmed buyers are imported." />
                )}
              </div>
              <div style={{ display: 'grid', gap: 8 }}>
                <DecisionStat light label="Best buyer" value={topBuyer?.buyer || 'None yet'} sub={topBuyer ? `${money(topBuyer.revenue)} · ${topBuyer.orders} orders` : 'Import orders first'} />
                <DecisionStat light label="Best region" value={bestRegion?.region || 'Unknown'} sub={bestRegion ? `${money(bestRegion.revenue)} · ${bestRegion.orders} orders` : 'Need shipping states'} />
              </div>
            </section>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <section style={decisionPanelStyle}>
              {sectionTitle('Customer Orders', selectedBuyer ? `${selectedBuyer}'s orders` : 'Click a customer to see orders', 'Every confirmed order for the selected buyer, with product, date, and amount.')}
              {selectedBuyerStats ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(120px, 1fr))', gap: 8, marginBottom: 10 }}>
                  <DecisionStat light label="Spend" value={money(selectedBuyerStats.revenue)} sub={selectedBuyerStats.segment} />
                  <DecisionStat light label="Orders" value={selectedBuyerStats.orders.toLocaleString()} sub={`AOV ${money(selectedBuyerStats.avgOrder)}`} />
                  <DecisionStat light label="Products" value={selectedBuyerStats.products.toLocaleString()} sub={selectedBuyerStats.primaryRegion} />
                  <DecisionStat light label="Last order" value={selectedBuyerStats.daysSinceLast == null ? 'Unknown' : `${selectedBuyerStats.daysSinceLast}d`} sub="days ago" />
                </div>
              ) : null}
              <div style={{ maxHeight: 340, overflow: 'auto', paddingRight: 4 }}>
                {selectedBuyerOrders.map((row) => {
                  const dt = dateValue(row);
                  const product = row.first_product_name || row.product_name || 'Unknown product';
                  return listRow(
                    product,
                    money(orderAmount(row)),
                    `${row.name || row.order_number || 'Order'} · ${dt ? dt.toLocaleDateString() : 'No date'} · ${row.fulfillment_status || 'pending'}`,
                  );
                })}
                {!selectedBuyer ? <EmptyInsight title="No customer selected" text="Click any customer in Who to target next to inspect all their orders." /> : null}
                {selectedBuyer && !selectedBuyerOrders.length ? <EmptyInsight title="No orders found" text="This buyer has no confirmed orders in the current TikTok slice." /> : null}
              </div>
            </section>

            <section style={decisionPanelStyle}>
              {sectionTitle('Geo Analysis', 'Where your TikTok buyers are', 'Revenue, buyer count, AOV, and top product by state or region.')}
              <div style={{ height: 230 }}>
                {regionStats.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={regionStats.slice(0, 8)}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.22)" />
                      <XAxis dataKey="region" tick={{ fill: '#64748b', fontSize: 11 }} />
                      <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                      <Tooltip formatter={(value, name) => [name === 'orders' || name === 'buyers' ? value : money(value), name]} />
                      <Bar dataKey="revenue" fill="#0f766e" radius={[8, 8, 0, 0]} />
                      <Bar dataKey="aov" fill="#f59e0b" radius={[8, 8, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyInsight title="No geo data yet" text="CSV/customer import needs shipping state or region fields for geo analysis." />
                )}
              </div>
              {regionStats.slice(0, 6).map((item) => listRow(item.region, money(item.revenue), `${item.orders} orders · ${item.buyers} buyers · AOV ${money(item.aov)} · Top: ${item.topProduct}`))}
            </section>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 }}>
            <section style={decisionPanelStyle}>
              {sectionTitle('Buyer Profiles', 'Top buyers with product taste', 'What each customer tends to buy, so the host knows what to show them.')}
              {buyerStats.slice(0, 8).map((item) => listRow(
                item.buyer,
                item.segment,
                `${item.productMix.slice(0, 3).map((product) => `${product.product} x${product.count}`).join(' · ') || 'No product mix'}`,
                {
                  active: selectedBuyer === item.buyer,
                  onClick: () => setSelectedBuyer(item.buyer),
                },
              ))}
              {!buyerStats.length ? <EmptyInsight title="No buyer profiles yet" text="Import confirmed orders to build buyer product taste." /> : null}
            </section>

            <section style={decisionPanelStyle}>
              {sectionTitle('Product Affinity', 'Buyer to product match', 'Great for shoutouts, bundles, and follow-up messages.')}
              {productAffinity.slice(0, 10).map((item) => listRow(item.buyer, `${item.orders}x`, `${item.product} · ${money(item.revenue)}`))}
              {!productAffinity.length ? <EmptyInsight title="No affinity yet" text="Product names and buyer names are needed to match customer taste." /> : null}
            </section>

            <section style={decisionPanelStyle}>
              {sectionTitle('Customer Actions', 'Decision engine', 'What to do before the next TikTok live.')}
              {listRow('Invite VIP repeats first', `${vipBuyers}`, topBuyer ? `Start with ${topBuyer.buyer}` : 'No VIP yet')}
              {listRow('Retarget one-time buyers', `${oneTimeBuyers}`, trendProduct ? `Lead with ${trendProduct.product}` : 'Need product trend')}
              {listRow('Protect concentration risk', `${(buyerConcentration * 100).toFixed(1)}%`, buyerConcentration > 0.55 ? 'Top buyers dominate revenue. Grow mid-tier buyers.' : 'Buyer base looks healthier.')}
              {listRow('Regional push', bestRegion?.region || 'Unknown', bestRegion ? `${bestRegion.orders} orders · ${money(bestRegion.revenue)}` : 'Need state data')}
            </section>
          </div>
        </div>
      ) : null}

      {analysisMode === 'returns' ? (
        <div style={{ display: 'grid', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(150px, 1fr))', gap: 12 }}>
            <DecisionStat light label="Returns pulled" value={(returnSummary.total || returnRows.length || 0).toLocaleString()} sub="TikTok return API rows" />
            <DecisionStat light label="Matched returns" value={matchedReturnRows.length.toLocaleString()} sub="matched to app orders" />
            <DecisionStat light label="Pending" value={numberValue(returnSummary.pending).toLocaleString()} sub="open TikTok returns" />
            <DecisionStat light label="Processed" value={numberValue(returnSummary.processed).toLocaleString()} sub="handled returns" />
            <DecisionStat light label="Refund total" value={money(returnSummary.refund_total || matchedReturnRows.reduce((sum, item) => sum + numberValue(item.total_refund_amount || item.refund_amount), 0))} sub="known refunds" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <section style={decisionPanelStyle}>
              {sectionTitle('Return Risk', 'Risk by product', 'Only returns whose TikTok order ID matches our TikTok Live order IDs are counted.')}
              {returnRiskProducts.slice(0, 12).map((item) => listRow(
                item.product,
                `${item.returns} returns`,
                `${item.buyers} buyers · refund ${money(item.refund)}`,
              ))}
              {!returnRiskProducts.length ? <EmptyInsight title="No matched product returns" text="Returns will appear here once TikTok return order IDs match app TikTok Live sale order IDs." /> : null}
            </section>

            <section style={decisionPanelStyle}>
              {sectionTitle('Customer Risk', 'Risk by customer', 'Useful for repeat return patterns and customer follow-up.')}
              {returnRiskCustomers.slice(0, 12).map((item) => listRow(
                item.buyer,
                `${item.returns} returns`,
                `refund ${money(item.refund)}`,
              ))}
              {!returnRiskCustomers.length ? <EmptyInsight title="No matched customer returns" text="Matched TikTok Live returns will populate this customer risk list." /> : null}
            </section>
          </div>

          <section style={decisionPanelStyle}>
            {sectionTitle('Matched Return Orders', 'Return records tied to app sales', 'This keeps shop returns from interfering with TikTok Live auction analysis.')}
            <div style={{ display: 'grid', gap: 6 }}>
              {matchedReturnRows.slice(0, 20).map((item) => {
                const saleOrder = item.saleOrder || {};
                return listRow(
                  item.order_id || item.return_id || saleOrder.name || 'TikTok return',
                  item.return_status || item.return_type || 'Return',
                  `${orderBuyer(saleOrder) || item.whatnot_buyer_username || 'Unknown buyer'} · ${saleOrder.first_product_name || saleOrder.product_name || 'Unknown product'} · refund ${money(item.total_refund_amount || item.refund_amount)}`,
                );
              })}
              {!matchedReturnRows.length ? <EmptyInsight title="No matched returns" text="The return feed loaded, but no return order IDs matched TikTok Live auction orders in the app." /> : null}
            </div>
          </section>
        </div>
      ) : null}

      {analysisMode === 'monthly' ? (
        <div style={{ display: 'grid', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(160px, 1fr))', gap: 12 }}>
            <DecisionStat light label="Months tracked" value={monthlyStats.length.toLocaleString()} sub="With TikTok orders" />
            <DecisionStat light label="Best month" value={bestMonth?.month || 'None'} sub={bestMonth ? money(bestMonth.revenue) : 'No month data'} />
            <DecisionStat light label="Monthly COGS" value={money(monthlyStats.reduce((sum, item) => sum + item.cogs, 0))} sub="All tracked months" />
            <DecisionStat light label="Monthly profit" value={money(monthlyStats.reduce((sum, item) => sum + item.profit, 0))} sub="after fees" />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 14 }}>
            <section style={decisionPanelStyle}>
              {sectionTitle('Monthly', 'COGS vs revenue trend', 'Use this to decide when to push bigger lives and promos.')}
              <div style={{ height: 310 }}>
                {monthlyStats.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={monthlyStats}>
                      <defs>
                        <linearGradient id="monthlyRevenueGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#6d5dfc" stopOpacity={0.32} />
                          <stop offset="95%" stopColor="#6d5dfc" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.22)" />
                      <XAxis dataKey="month" tick={{ fill: '#64748b', fontSize: 11 }} />
                      <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                      <Tooltip formatter={(value, name) => [name === 'revenue' || name === 'aov' ? money(value) : value, name]} />
                      <Area type="monotone" dataKey="revenue" stroke="#6d5dfc" fill="url(#monthlyRevenueGradient)" strokeWidth={3} />
                      <Line type="monotone" dataKey="cogs" stroke="#f97316" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="profit" stroke="#0f766e" strokeWidth={2} dot />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyInsight title="No monthly trend yet" text="Orders need dates so monthly performance can be grouped." />
                )}
              </div>
            </section>

            <section style={decisionPanelStyle}>
              {sectionTitle('Monthly Breakdown', 'Revenue, buyers, and AOV', 'Quick month-by-month performance read.')}
              {monthlyStats.slice().reverse().map((item) => listRow(item.month, money(item.profit), `${item.orders} orders · revenue ${money(item.revenue)} · COGS ${money(item.cogs)} · margin ${item.margin.toFixed(1)}%`))}
              {!monthlyStats.length ? <EmptyInsight title="No monthly data" text="Import dated TikTok orders to populate this view." /> : null}
            </section>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function DecisionStat({ label, value, sub, light = false }) {
  return (
    <div
      style={{
        borderRadius: 18,
        padding: light ? 14 : 13,
        background: light ? 'rgba(248,250,252,0.95)' : 'rgba(255,255,255,0.12)',
        border: light ? '1px solid rgba(226,232,240,0.95)' : '1px solid rgba(255,255,255,0.16)',
        color: light ? '#0f172a' : '#fff',
      }}
    >
      <div style={{ fontSize: 10, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase', color: light ? '#64748b' : 'rgba(255,255,255,0.66)' }}>{label}</div>
      <div style={{ marginTop: 6, fontSize: light ? 22 : 20, fontWeight: 950, letterSpacing: '-0.05em', lineHeight: 1 }}>{value}</div>
      {sub ? <div style={{ marginTop: 5, fontSize: 11, color: light ? '#64748b' : 'rgba(255,255,255,0.68)' }}>{sub}</div> : null}
    </div>
  );
}

function EmptyInsight({ title, text }) {
  return (
    <div style={{ padding: 18, borderRadius: 18, background: 'rgba(248,250,252,0.95)', border: '1px dashed rgba(148,163,184,0.45)', color: '#64748b' }}>
      <div style={{ fontWeight: 900, color: '#334155', marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 13, lineHeight: 1.55 }}>{text}</div>
    </div>
  );
}

function UploadsWorkspace({ activeSection = 'uploads' }) {
  const showOverview = activeSection === 'uploads';
  const showTikTok = activeSection === 'uploads' || activeSection === 'uploads-tiktok';
  const showAffiliate = activeSection === 'uploads' || activeSection === 'uploads-affiliate';

  return (
    <div className="enterprise-workspace">
      {showOverview ? (
        <div className="enterprise-section-grid">
          <Panel title="Whatnot Live Capture">
            <div style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.6 }}>
              Whatnot is captured directly during live sessions. Use Control Tower for live capture and review.
            </div>
          </Panel>
          <Panel title="TikTok CSV Uploads">
            <div style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.6 }}>
              TikTok Shop uses one CSV upload. TikTok Live auctions use two sheets after the event, then everything is merged into sales orders.
            </div>
          </Panel>
          <Panel title="Partner CSV Uploads">
            <div style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.6 }}>
              Partners only use scanner, TV display, and assigned-pricelist inventory. Their sales are uploaded later by CSV.
            </div>
          </Panel>
        </div>
      ) : null}

      {showTikTok ? (
        <div style={{ display: 'grid', gap: 14 }}>
          <TikTokShopOrders
            source="tiktok_shop"
            title="TikTok Shop CSV Upload"
            importTitle="Import TikTok Shop CSV"
            emptyMessage="No TikTok Shop CSV imports yet."
            showCreate={false}
            showImport
          />
          <TikTokShopOrders
            source="tiktok_live"
            title="TikTok Live CSV Upload"
            importTitle="Import TikTok Live CSV"
            emptyMessage="No TikTok Live CSV imports yet."
            showCreate={false}
            showImport
          />
        </div>
      ) : null}

      {showAffiliate ? (
        <Panel title="Partner CSV Upload">
          <div style={{ display: 'grid', gap: 12 }}>
            <div style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.6 }}>
              Partner CSV uploads should create the same sales order records as Whatnot and TikTok. Each row should include partner, buyer/customer, product or SKU, quantity, sale price, platform/date, and fulfillment details when available.
            </div>
            <div style={{ border: '1px solid #e6e8ee', borderRadius: 12, padding: 14, background: '#f7fafc', color: '#3c4257', fontSize: 13, fontWeight: 700 }}>
              Backend import endpoint is the next piece for this source. The navigation and sales filters are now structured for partner / affiliate CSV sales.
            </div>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}

function tone(value, warn = 15, good = 25) {
  if (value == null) return 'var(--text-secondary)';
  if (value >= good) return 'var(--accent-emerald)';
  if (value >= warn) return 'var(--accent-amber)';
  return 'var(--accent-coral)';
}

function StatusPill({ status }) {
  const palette = {
    live: { label: 'LIVE', bg: 'rgba(34,197,94,0.15)', border: 'rgba(34,197,94,0.32)', color: 'var(--accent-emerald)' },
    draft: { label: 'Draft', bg: 'rgba(245,158,11,0.16)', border: 'rgba(245,158,11,0.26)', color: '#fbbf24' },
    ended: { label: 'Ended', bg: 'var(--bg-elevated)', border: 'var(--border-default)', color: 'var(--text-secondary)' },
  };
  const badge = palette[status] || palette.ended;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 10px',
        borderRadius: 999,
        border: `1px solid ${badge.border}`,
        background: badge.bg,
        color: badge.color,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.06em',
      }}
    >
      {status === 'live' && <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'currentColor' }} />}
      {badge.label}
    </span>
  );
}

function KpiCard({ label, value, sub, color, onClick, style }) {
  return (
    <button
      className="company-kpi"
      type="button"
      onClick={onClick}
      style={{
        borderRadius: 'var(--radius-lg)',
        padding: '18px 20px',
        textAlign: 'left',
        cursor: onClick ? 'pointer' : 'default',
        width: '100%',
        color: 'inherit',
        ...style,
      }}
    >
      <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 800, color: color || 'var(--text-primary)', lineHeight: 1, letterSpacing: '-0.02em' }}>{value}</div>
      {sub ? <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 5 }}>{sub}</div> : null}
    </button>
  );
}

function Panel({ title, children, action }) {
  return (
    <section className="company-panel">
      <div className="company-panel-head">
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600, letterSpacing: '0.04em' }}>{title}</div>
        {action}
      </div>
      <div className="company-panel-body">{children}</div>
    </section>
  );
}

function AdminActionCard({ icon: Icon, eyebrow, title, description, tab, to, onTabChange, accent = 'rgba(245,158,11,0.16)' }) {
  const content = (
    <>
      <div
        style={{
          width: 42,
          height: 42,
          borderRadius: 16,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: accent,
          color: '#92400e',
          flexShrink: 0,
        }}
      >
        {Icon ? <Icon size={20} strokeWidth={2.2} /> : null}
      </div>
      <div style={{ minWidth: 0 }}>
        {eyebrow ? <div style={{ fontSize: 10, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#a5957c', marginBottom: 5 }}>{eyebrow}</div> : null}
        <div style={{ fontSize: 17, fontWeight: 900, letterSpacing: '-0.03em', color: '#0f172a' }}>{title}</div>
        <div style={{ marginTop: 6, fontSize: 13, lineHeight: 1.55, color: '#6f6557' }}>{description}</div>
      </div>
    </>
  );

  const sharedStyle = {
    minHeight: 146,
    border: '1px solid rgba(229,209,177,0.54)',
    borderRadius: 24,
    background: 'linear-gradient(180deg, rgba(255,255,255,0.96), rgba(255,248,238,0.92))',
    padding: 18,
    display: 'flex',
    gap: 14,
    textAlign: 'left',
    textDecoration: 'none',
    color: 'inherit',
    cursor: 'pointer',
    boxShadow: '0 16px 36px rgba(125,91,36,0.07)',
  };

  if (to) return <Link to={to} style={sharedStyle}>{content}</Link>;
  return (
    <button type="button" onClick={() => tab && onTabChange(tab)} style={sharedStyle}>
      {content}
    </button>
  );
}

function AdminCardGrid({ children }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(245px, 1fr))', gap: 14 }}>
      {children}
    </div>
  );
}

function AuctionResultsHub({ onTabChange }) {
  return (
    <Panel title="Auction results">
      <AdminCardGrid>
        <AdminActionCard
          icon={FileBarChart2}
          eyebrow="Whatnot Live"
          title="Whatnot Live"
          description="Review Whatnot auction winners, payment exceptions, product profit, fees, and order sync."
          tab="auction-results"
          onTabChange={onTabChange}
        />
        <AdminActionCard
          icon={Sparkles}
          eyebrow="TikTok Live"
          title="TikTok Live"
          description="Review TikTok Live auction captures separately so the channel stays clean and easier to reconcile."
          tab="tiktok"
          onTabChange={onTabChange}
        />
      </AdminCardGrid>
    </Panel>
  );
}

function OurCompanyHub({ sessions, inventory, saleOrders, onTabChange }) {
  const liveCount = sessions.filter((session) => session.status === 'live').length;
  const tiktokCount = sessions.filter((session) => isTikTokSession(session)).length;
  const orderCount = saleOrders.confirmed_count || (saleOrders.rows || []).filter((row) => row.state === 'sale').length;
  const productCount = inventory.total_products ?? (inventory.rows || []).length ?? 0;

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
        <KpiCard label="Live Sessions" value={liveCount} color={liveCount ? 'var(--accent-emerald)' : undefined} />
        <KpiCard label="TikTok Sessions" value={tiktokCount} color="var(--accent-amber)" />
        <KpiCard label="Confirmed Orders" value={orderCount} color="var(--accent-emerald)" />
        <KpiCard label="Inventory Products" value={productCount} />
      </div>

      <Panel title="YNF Deals operations">
        <AdminCardGrid>
          <AdminActionCard icon={LayoutDashboard} eyebrow="Company admin" title="Dashboard" description="Executive KPIs, live state, alerts, and company-wide action items for the YNF Deals account." tab="overview" onTabChange={onTabChange} />
          <AdminActionCard icon={FileBarChart2} eyebrow="Channels" title="Channel Results" description="Choose Whatnot Live, TikTok Live, or TikTok Shop without mixing review flows." tab="auction-results-hub" onTabChange={onTabChange} />
          <AdminActionCard icon={Receipt} eyebrow="Operations" title="Sales" description="Manage Whatnot orders, TikTok Shop orders, TikTok Live auctions, partner uploads, and in-house sales." tab="orders" onTabChange={onTabChange} />
          <AdminActionCard icon={ShoppingBag} eyebrow="Internal" title="In-House Sales" description="Track employee purchases and internal inventory movement." tab="in-house-sales" onTabChange={onTabChange} />
          <AdminActionCard icon={Receipt} eyebrow="TikTok" title="TikTok Live Auctions" description="Open the TikTok Live auction queue generated from confirmed winner scans and uploaded sheets." tab="tiktok-live-sales" onTabChange={onTabChange} />
          <AdminActionCard icon={ShoppingBag} eyebrow="TikTok" title="TikTok Shop Sales" description="Review TikTok Shop sales separately from livestream tickets." tab="tiktok-shop-sales" onTabChange={onTabChange} />
          <AdminActionCard icon={Users2} eyebrow="Partners" title="Partner Orders" description="Review uploaded partner sales separately from Whatnot, TikTok Shop, TikTok Live, and in-house sales." tab="orders-affiliate" onTabChange={onTabChange} />
        </AdminCardGrid>
      </Panel>
    </div>
  );
}

function FinanceHub() {
  const [data, setData] = useState(null);
  const [activeView, setActiveView] = useState('overview');
  const [query, setQuery] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [importingIncome, setImportingIncome] = useState(false);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const incomeInputRef = useRef(null);

  const loadFinance = async (opts = {}) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (opts.q || query) params.set('q', opts.q || query);
      params.set('session_min', '1');
      params.set('session_max', '20');
      params.set('ordered_from', '2026-04-17');
      const result = await fetchApi(`/api/v2/integrations/tiktok-shop/finance/overview${params.toString() ? `?${params.toString()}` : ''}`);
      setData(result);
      setMessage(result?.guardrail || '');
    } catch (err) {
      setMessage(err?.message || 'Could not load finance reconciliation.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFinance();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const syncSettlements = async () => {
    setSyncing(true);
    setMessage('Pulling TikTok payout details for orders already saved in YNF...');
    try {
      const result = await postApi('/api/v2/integrations/tiktok-shop/finance/sync', {
        limit: 100,
        q: query || undefined,
        session_min: 1,
        session_max: 20,
        ordered_from: '2026-04-17',
      });
      setMessage(`Done: ${result.synced || 0} orders updated, ${result.failed || 0} failed, ${result.known_order_count || 0} YNF orders checked.`);
      await loadFinance();
    } catch (err) {
      setMessage(err?.message || 'Could not pull TikTok payout details.');
    } finally {
      setSyncing(false);
    }
  };

  const importIncomeFile = async (file) => {
    if (!file) return;
    setImportingIncome(true);
    setMessage(`Importing TikTok income file: ${file.name}...`);
    try {
      const form = new FormData();
      form.append('file', file, file.name);
      const csrf = getStoredCsrfToken();
      const res = await fetch('/api/v2/integrations/tiktok-shop/finance/import-income', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
        body: form,
      });
      const result = await res.json().catch(() => ({}));
      if (!res.ok || result?.ok === false) {
        throw new Error(result?.error || `Import failed (${res.status})`);
      }
      setMessage(
        `Income imported: ${result.imported || 0} local rows matched. Matched shipping: customer ${fmt(result.customer_shipping || 0)}, our cost ${fmt(result.shipping_cost || 0)}. Full file shipping: customer ${fmt(result.workbook_customer_shipping || 0)}, our cost ${fmt(result.workbook_shipping_cost || 0)}.`
      );
      await loadFinance();
    } catch (err) {
      setMessage(err?.message || 'Could not import TikTok income file.');
    } finally {
      setImportingIncome(false);
      if (incomeInputRef.current) incomeInputRef.current.value = '';
    }
  };

  const totals = data?.totals || {};
  const financeRows = activeView === 'exceptions'
    ? (data?.exceptions || [])
    : activeView === 'sessions'
      ? (data?.sessions || [])
      : (data?.orders || []).slice(0, 250);
  const difference = Number(totals.unreconciled_difference || 0);
  const shippingNet = Number(totals.shipping_charged || 0) - Number(totals.shipping_cost || 0);
  const cleanDifference = Math.abs(difference) < 0.01;
  const financeTabs = [
    ['overview', 'Summary'],
    ['sessions', 'By Session'],
    ['orders', 'By Order'],
    ['exceptions', 'Problems'],
  ];
  const moneyBreakdown = [
    ['Customers paid', totals.revenue, 'Total sales captured from our saved TikTok orders.'],
    ['Minus product cost', -Number(totals.cogs || 0), 'Our inventory cost for those items.'],
    ['Minus TikTok fees', -Number(totals.fees || 0), 'Platform fees we know about.'],
    ['Plus customer shipping', totals.shipping_charged, 'Shipping money paid by the customer.'],
    ['Minus our shipping cost', -Number(totals.shipping_cost || 0), 'What shipping cost us.'],
    ['Estimated profit', totals.estimated_profit, 'Revenue minus costs, fees, and shipping difference.'],
  ];
  const metricCards = [
    ['Sales', totals.revenue, 'What customers paid', '#0f172a'],
    ['Product Cost', totals.cogs, 'Cost of goods', '#0f172a'],
    ['TikTok Fees', totals.fees, 'Platform charges', '#b45309'],
    ['Customer Shipping', totals.shipping_charged, 'Shipping collected', '#0f172a'],
    ['Our Shipping', totals.shipping_cost, 'Shipping paid by us', Number(totals.shipping_cost || 0) > Number(totals.shipping_charged || 0) ? '#dc2626' : '#0f172a'],
    ['Profit', totals.estimated_profit, 'After known costs', Number(totals.estimated_profit || 0) >= 0 ? '#047857' : '#dc2626'],
    ['TikTok Payout', totals.payout_received, 'Money TikTok reports', '#0f172a'],
    ['Difference', difference, 'Needs review if not zero', cleanDifference ? '#047857' : '#dc2626'],
  ];

  return (
    <div style={{ display: 'grid', gap: 14, maxWidth: 1680 }}>
      <section className="company-panel" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, padding: '16px 18px 12px', borderBottom: '1px solid var(--border-default)' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <BarChart3 size={17} color="#0f172a" />
              <h2 style={{ margin: 0, fontSize: 22, letterSpacing: '-0.02em' }}>Finance Reports</h2>
              <span style={{ fontSize: 11, fontWeight: 800, color: cleanDifference ? '#047857' : '#dc2626', background: cleanDifference ? '#ecfdf5' : '#fef2f2', border: `1px solid ${cleanDifference ? '#bbf7d0' : '#fecaca'}`, borderRadius: 999, padding: '4px 8px' }}>
                {cleanDifference ? 'Looks clean' : 'Needs review'}
              </span>
            </div>
            <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
              Go Live sessions 1-20 from April 17, 2026 onward: customer payments, product cost, TikTok fees, shipping, payouts, and profit.
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            <button type="button" className="company-ghost-btn" onClick={() => loadFinance()} disabled={loading}>Refresh</button>
            <input
              ref={incomeInputRef}
              type="file"
              accept=".xlsx"
              style={{ display: 'none' }}
              onChange={(event) => importIncomeFile(event.target.files?.[0])}
            />
            <button type="button" className="company-ghost-btn" onClick={() => incomeInputRef.current?.click()} disabled={importingIncome}>
              {importingIncome ? 'Importing...' : 'Import Income XLSX'}
            </button>
            <button type="button" className="company-primary-btn" onClick={syncSettlements} disabled={syncing}>{syncing ? 'Pulling...' : 'Pull TikTok Payouts'}</button>
          </div>
        </div>
        {message ? (
          <div style={{ padding: '10px 20px', fontSize: 12, color: '#475569', borderBottom: '1px solid var(--border-default)', background: '#f8fafc' }}>{message}</div>
        ) : null}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', borderBottom: '1px solid var(--border-default)' }}>
          {metricCards.map(([label, value, detail, color]) => (
            <div key={label} style={{ padding: '12px 14px', borderRight: '1px solid var(--border-default)', minHeight: 76 }}>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '.07em' }}>{label}</div>
              <div style={{ fontSize: 18, fontWeight: 900, color, marginTop: 7 }}>{fmt(value || 0)}</div>
              <div style={{ color: 'var(--text-secondary)', fontSize: 11, marginTop: 3 }}>{detail}</div>
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 20px' }}>
          {financeTabs.map(([view, label]) => (
            <button
              key={view}
              type="button"
              className={activeView === view ? 'company-primary-btn' : 'company-ghost-btn'}
              onClick={() => setActiveView(view)}
              style={{ padding: '8px 11px' }}
            >
              {label}
            </button>
          ))}
          <div style={{ flex: 1 }} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') loadFinance({ q: query });
            }}
            placeholder="Search order ID, buyer, or session..."
            style={{ minWidth: 320, border: '1px solid var(--border-default)', borderRadius: 10, padding: '9px 12px', fontSize: 13 }}
          />
          <button type="button" className="company-ghost-btn" onClick={() => loadFinance({ q: query })}>Search</button>
        </div>
      </section>

      {activeView === 'overview' ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.1fr) minmax(320px, .9fr)', gap: 14 }}>
          <Panel title="Start here">
            <div style={{ display: 'grid', gap: 10, fontSize: 13, lineHeight: 1.55 }}>
              <div><strong>1. Scope:</strong> only paid, non-cancelled TikTok Live orders from Go Live sessions 1-20, starting April 17, 2026, are included.</div>
              <div><strong>2. Pull TikTok payouts</strong> to fetch settled statement transactions for those known order IDs.</div>
              <div><strong>3. Check Difference.</strong> If it is not zero, open <strong>Problems</strong> and review shipping/fees/order mapping.</div>
              <div><strong>4. Open By Session</strong> to see which live shows made or lost money.</div>
              <div style={{ marginTop: 4, color: 'var(--text-secondary)' }}>This page does not create orders and does not deduct inventory. Today’s unsettled orders may show internal estimates until TikTok posts statement transactions.</div>
            </div>
          </Panel>
          <Panel title="Where the money went">
            <div style={{ display: 'grid', gap: 0 }}>
              {moneyBreakdown.map(([label, value, help], index) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: index === moneyBreakdown.length - 1 ? 0 : '1px solid var(--border-default)', fontSize: 13 }}>
                  <div>
                    <div style={{ color: index === moneyBreakdown.length - 1 ? 'var(--text-primary)' : 'var(--text-secondary)', fontWeight: index === moneyBreakdown.length - 1 ? 900 : 700 }}>{label}</div>
                    <div style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{help}</div>
                  </div>
                  <span style={{ color: Number(value || 0) < 0 ? '#dc2626' : '#047857', fontWeight: 900, whiteSpace: 'nowrap' }}>{fmt(value || 0)}</span>
                </div>
              ))}
            </div>
          </Panel>
          <Panel title="Quick checks">
            <div style={{ display: 'grid', gap: 12, fontSize: 13 }}>
              <div><strong>{totals.orders || 0}</strong> saved TikTok orders are included.</div>
              <div><strong>{totals.matched_finance_orders || 0}</strong> orders have TikTok finance records saved.</div>
              <div><strong>{totals.missing_finance_orders || 0}</strong> included orders are still missing TikTok finance records.</div>
              <div style={{ color: shippingNet >= 0 ? '#047857' : '#dc2626', fontWeight: 900 }}>
                Shipping net: {fmt(shippingNet)} {shippingNet >= 0 ? '(collected enough)' : '(we paid more than customer paid)'}
              </div>
              <div style={{ color: cleanDifference ? '#047857' : '#dc2626', fontWeight: 900 }}>
                Difference: {fmt(difference)} {cleanDifference ? '(clean)' : '(review needed)'}
              </div>
            </div>
          </Panel>
        </div>
      ) : null}

      <Panel
        title={activeView === 'sessions' ? 'Money by live session' : activeView === 'exceptions' ? 'Problems to review' : 'Money by order'}
        action={<span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{loading ? 'Loading...' : `${financeRows.length} rows`}</span>}
      >
        <div style={{ overflowX: 'auto' }}>
          {activeView === 'sessions' ? (
            <table className="company-table">
              <thead><tr><th>Session</th><th>Orders</th><th>Sales</th><th>Product Cost</th><th>TikTok Fees</th><th>Customer Shipping</th><th>Our Shipping</th><th>TikTok Payout</th><th>Profit</th><th>Margin</th><th>Status</th></tr></thead>
              <tbody>
                {financeRows.map((row) => (
                  <tr key={row.session_id || row.session_name}>
                    <td style={{ fontWeight: 800 }}>{row.session_name || 'Unassigned'}</td>
                    <td>{row.orders}</td>
                    <td>{fmt(row.revenue)}</td>
                    <td>{fmt(row.cogs)}</td>
                    <td>{fmt(row.fees)}</td>
                    <td>{fmt(row.shipping_charged)}</td>
                    <td>{fmt(row.shipping_cost)}</td>
                    <td>{fmt(row.payout_received)}</td>
                    <td style={{ color: Number(row.profit || 0) >= 0 ? '#047857' : '#dc2626', fontWeight: 900 }}>{fmt(row.profit)}</td>
                    <td>{Number(row.margin_pct || 0).toFixed(1)}%</td>
                    <td>{row.settlement_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className="company-table">
              <thead><tr><th>Order ID</th><th>Session</th><th>Buyer</th><th>Order Status</th><th>Sales</th><th>Product Cost</th><th>TikTok Fees</th><th>Customer Shipping</th><th>Our Shipping</th><th>TikTok Payout</th><th>Profit</th><th>Payout Status</th></tr></thead>
              <tbody>
                {financeRows.map((row) => (
                  <tr key={row.sale_order_id}>
                    <td style={{ fontWeight: 900 }}>{row.tiktok_order_id || row.order_number}</td>
                    <td>{row.session_name || '—'}</td>
                    <td>{row.buyer || '—'}</td>
                    <td>{row.status || row.payment_status || '—'}</td>
                    <td>{fmt(row.revenue)}</td>
                    <td>{fmt(row.cogs)}</td>
                    <td>{fmt(row.fees)}</td>
                    <td>{fmt(row.shipping_charged)}</td>
                    <td>{fmt(row.shipping_cost)}</td>
                    <td>{fmt(row.payout_received)}</td>
                    <td style={{ color: Number(row.profit || 0) >= 0 ? '#047857' : '#dc2626', fontWeight: 900 }}>{fmt(row.profit)}</td>
                    <td style={{ color: row.settlement_status === 'sync_failed' ? '#dc2626' : 'var(--text-secondary)', fontWeight: 800 }}>{row.settlement_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!loading && !financeRows.length ? <div style={{ padding: 24, color: 'var(--text-secondary)', textAlign: 'center' }}>No finance rows found.</div> : null}
        </div>
      </Panel>
    </div>
  );
}

function AccountPlaceholder({ activeSection }) {
  const copy = {
    accounts: {
      title: 'Partners',
      body: 'This is the control center for partner accounts, delegated partner users, access permissions, channels, and assigned pricelists.',
    },
    'affiliate-accounts': {
      title: 'Partner Accounts',
      body: 'Next backend step: create partner account records with owner, status, pricelist, inventory scope, progress metrics, and audit history.',
    },
    'affiliate-user-management': {
      title: 'Partner User Management',
      body: 'Next backend step: let each partner add their own users inside their account while admins keep final control over roles and access.',
    },
    'access-permissions': {
      title: 'Access & Permissions',
      body: 'Use this area to explicitly map TV scanner, TV display, inventory, and user-management permissions before routes are exposed.',
    },
    'tv-scanner-access': {
      title: 'TV Scanner Access',
      body: 'Grant scanner page access only to users or partners that have the right inventory and pricelist scope.',
    },
    'tv-display-access': {
      title: 'TV Display Access',
      body: 'Grant display-only access for floor screens without giving write access to inventory, orders, or user management.',
    },
    'inventory-access': {
      title: 'Inventory Access',
      body: 'Inventory should stay hidden until a user has both an access grant and an assigned pricelist.',
    },
    'user-management-access': {
      title: 'User Management Access',
      body: 'This should become the explicit permission gate for adding staff users, affiliate users, or changing roles.',
    },
    'assigned-pricelists': {
      title: 'Assigned Pricelists',
      body: 'Review who is assigned to retail, staff, affiliate, wholesale, or scanner/display pricing before inventory loads for them.',
    },
  };
  const item = copy[activeSection] || copy.accounts;
  return (
    <Panel title={item.title}>
      <div style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.65 }}>{item.body}</div>
    </Panel>
  );
}

function EnterpriseMetric({ label, value, detail, tone = 'neutral' }) {
  return (
    <div className={`enterprise-metric enterprise-metric--${tone}`}>
      <div className="enterprise-metric__label">{label}</div>
      <div className="enterprise-metric__value">{value}</div>
      <div className="enterprise-metric__detail">{detail}</div>
    </div>
  );
}

function AccessDomainCard({ icon: Icon, title, owner, description, status, tone = 'neutral' }) {
  return (
    <div className={`access-domain-card access-domain-card--${tone}`}>
      <div className="access-domain-card__head">
        <div className="access-domain-card__icon">{Icon ? <Icon size={18} /> : null}</div>
        <span className="access-domain-card__status">{status}</span>
      </div>
      <div className="access-domain-card__title">{title}</div>
      <div className="access-domain-card__owner">{owner}</div>
      <div className="access-domain-card__description">{description}</div>
    </div>
  );
}

function RoleMatrix() {
  const rows = [
    { capability: 'Company administration', admin: 'Full', staffWrite: 'No', staffRead: 'No', owner: 'No', user: 'No' },
    { capability: 'Affiliate accounts', admin: 'Full', staffWrite: 'Read', staffRead: 'Read', owner: 'Own account', user: 'Own account' },
    { capability: 'Affiliate user management', admin: 'Full', staffWrite: 'No', staffRead: 'No', owner: 'Own users', user: 'No' },
    { capability: 'Inventory visibility rules', admin: 'Full', staffWrite: 'Operate', staffRead: 'Read', owner: 'Assigned only', user: 'Assigned only' },
    { capability: 'Pricelist assignment', admin: 'Full', staffWrite: 'No', staffRead: 'No', owner: 'No', user: 'No' },
    { capability: 'TV scanner/display', admin: 'Full', staffWrite: 'If granted', staffRead: 'No', owner: 'If granted', user: 'If granted' },
    { capability: 'Security and sessions', admin: 'Full', staffWrite: 'Limited', staffRead: 'Read', owner: 'Own users', user: 'Own session' },
  ];
  const columns = [
    ['admin', 'Admin'],
    ['staffWrite', 'Staff Write'],
    ['staffRead', 'Staff Read'],
    ['owner', 'Affiliate Owner'],
    ['user', 'Affiliate User'],
  ];

  return (
    <div className="company-table-shell enterprise-table-shell">
      <table className="enterprise-matrix-table">
        <thead>
          <tr>
            <th>Capability</th>
            {columns.map(([, label]) => <th key={label}>{label}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.capability}>
              <td><strong>{row.capability}</strong></td>
              {columns.map(([key]) => (
                <td key={key}>
                  <span className={row[key] === 'Full' ? 'matrix-chip matrix-chip--full' : row[key] === 'No' ? 'matrix-chip matrix-chip--none' : 'matrix-chip'}>
                    {row[key]}
                  </span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AccessControlOverview({ onTabChange }) {
  const domains = [
    {
      icon: UserCog,
      title: 'Staff Identity',
      owner: 'Admin-owned',
      status: 'RBAC gated',
      tone: 'blue',
      description: 'Internal users, sessions, POS links, and operational roles belong here.',
      tab: 'staff-users',
    },
    {
      icon: Network,
      title: 'Affiliate Boundaries',
      owner: 'Delegated access',
      status: 'Scoped',
      tone: 'emerald',
      description: 'Affiliate users can operate only inside their account, inventory scope, and pricelist.',
      tab: 'affiliate-user-management',
    },
    {
      icon: Database,
      title: 'Inventory Exposure',
      owner: 'Pricelist + visibility',
      status: 'Controlled',
      tone: 'amber',
      description: 'Products are visible only when assigned, allowed, and priced for that affiliate.',
      tab: 'inventory-access',
    },
    {
      icon: Monitor,
      title: 'TV Workflows',
      owner: 'Floor tools',
      status: 'Feature-gated',
      tone: 'neutral',
      description: 'Scanner and display access stay separate from admin and inventory write access.',
      tab: 'tv-scanner-access',
    },
  ];

  return (
    <div className="enterprise-console">
      <section className="enterprise-hero-panel">
        <div className="enterprise-hero-panel__content">
          <div className="enterprise-eyebrow">Identity, access, and affiliate governance</div>
          <h2>Enterprise access control plane</h2>
          <p>
            Replace broad “authenticated user” behavior with explicit roles, bounded affiliate access,
            auditable mutations, and workflow-specific grants for scanner, display, inventory, and user administration.
          </p>
        </div>
        <div className="enterprise-hero-panel__actions">
          <button type="button" className="company-primary-btn" onClick={() => onTabChange('access-permissions')}>Review Role Matrix</button>
          <button type="button" className="company-ghost-btn" onClick={() => onTabChange('diagnostics')}>Open Diagnostics</button>
        </div>
      </section>

      <div className="enterprise-metric-grid">
        <EnterpriseMetric label="Role Model" value="5 roles" detail="admin, staff read/write, affiliate owner/user" tone="blue" />
        <EnterpriseMetric label="Sensitive Routes" value="Admin gated" detail="affiliate management, auth users, POS token controls" tone="emerald" />
        <EnterpriseMetric label="Inventory Exposure" value="Pricelist first" detail="no affiliate catalog without pricing and visibility rules" tone="amber" />
        <EnterpriseMetric label="Audit Posture" value="Tracked" detail="auth, admin mutation, affiliate inventory, diagnostics" tone="neutral" />
      </div>

      <div className="enterprise-section-grid">
        <Panel title="Permission matrix">
          <RoleMatrix />
        </Panel>
        <Panel title="Governance notes">
          <div className="governance-list">
            <div><AlertTriangle size={16} /><span>Staff roles must not mutate affiliate management routes unless explicitly promoted.</span></div>
            <div><ShieldCheck size={16} /><span>Affiliate owners manage only their own users and assigned product catalog.</span></div>
            <div><KeyRound size={16} /><span>User-management access is a security workflow, not a generic page link.</span></div>
            <div><Database size={16} /><span>Affiliate inventory preview must never expose cost price or unassigned products.</span></div>
          </div>
        </Panel>
      </div>

      <Panel title="Access domains">
        <div className="access-domain-grid">
          {domains.map((domain) => (
            <button key={domain.title} type="button" className="access-domain-button" onClick={() => onTabChange(domain.tab)}>
              <AccessDomainCard {...domain} />
            </button>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function AccountsHub({ activeSection = 'accounts', onTabChange }) {
  const showAccessConsole = ['access-permissions', 'tv-scanner-access', 'tv-display-access', 'user-management-access'].includes(activeSection);
  return (
    <div className="enterprise-workspace">
      {showAccessConsole ? <AccessControlOverview activeSection={activeSection} onTabChange={onTabChange} /> : null}

      {activeSection === 'staff-users' ? <EmployeeManagement /> : <AccountPlaceholder activeSection={activeSection} />}
    </div>
  );
}

function PricelistsWorkspace({ onTabChange }) {
  const tiers = [
    { name: 'Retail', owner: 'Public/company default', status: 'Current default', note: 'Used for standard dashboard retail pricing.' },
    { name: 'Staff', owner: 'Internal employees', status: 'Needs policy', note: 'Use for in-house sales and employee checkout rules.' },
    { name: 'Affiliate', owner: 'Affiliate users', status: 'Needs buildout', note: 'Apply before affiliates can see inventory or create delegated users.' },
    { name: 'Wholesale', owner: 'Bulk buyers', status: 'Draft', note: 'Reserve for volume discounts and non-live sales workflows.' },
    { name: 'TV Scanner', owner: 'Floor display/scanner', status: 'Needs mapping', note: 'Control what price appears on TV scanner and display pages.' },
  ];

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <Panel title="Pricelist setup path">
        <div style={{ display: 'grid', gap: 12 }}>
          {[
            'Define pricelist tiers and whether they discount from retail, cost, or fixed channel price.',
            'Assign each user or affiliate account to exactly one default pricelist.',
            'Apply inventory visibility rules before exposing products to affiliates.',
            'Use audit logs when a pricelist is changed, assigned, revoked, or used on an order.',
          ].map((step, index) => (
            <div key={step} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', padding: 14, borderRadius: 18, background: 'rgba(255,255,255,0.72)', border: '1px solid rgba(229,209,177,0.45)' }}>
              <div style={{ width: 28, height: 28, borderRadius: 999, background: 'rgba(245,158,11,0.16)', color: '#92400e', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900 }}>{index + 1}</div>
              <div style={{ color: '#584b3c', fontSize: 14, lineHeight: 1.55 }}>{step}</div>
            </div>
          ))}
        </div>
      </Panel>

      <div className="company-table-shell">
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              {['Pricelist', 'Audience', 'Status', 'Notes'].map((heading) => <th key={heading} style={{ padding: '12px 14px', textAlign: 'left' }}>{heading}</th>)}
            </tr>
          </thead>
          <tbody>
            {tiers.map((tier) => (
              <tr key={tier.name} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                <td style={{ padding: '12px 14px', fontWeight: 900 }}>{tier.name}</td>
                <td style={{ padding: '12px 14px', color: 'var(--text-secondary)' }}>{tier.owner}</td>
                <td style={{ padding: '12px 14px' }}><StatusPill status={tier.status === 'Current default' ? 'live' : 'draft'} /></td>
                <td style={{ padding: '12px 14px', color: 'var(--text-secondary)' }}>{tier.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Panel
        title="Next backend build"
        action={<button type="button" className="company-ghost-btn" onClick={() => onTabChange('accounts')}>Open Accounts</button>}
      >
        <div style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.65 }}>
          This page is the new admin home for pricelists. The next implementation step is adding persistent pricelist tables, user-to-pricelist assignments, and inventory API filters that apply those rules before affiliate inventory loads.
        </div>
      </Panel>
    </div>
  );
}

function MetricRow({ label, value, valueColor, sub, onClick, last }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '13px 20px',
        background: 'transparent',
        border: 'none',
        borderBottom: last ? 'none' : '1px solid var(--border-subtle)',
        outline: 'none',
        width: '100%',
        cursor: onClick ? 'pointer' : 'default',
        textAlign: 'left',
        transition: 'background 0.15s',
      }}
      onMouseEnter={(e) => onClick && (e.currentTarget.style.background = 'var(--bg-hover)')}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
    >
      <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{label}</span>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: valueColor || 'var(--text-primary)' }}>{value}</div>
        {sub && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 1 }}>{sub}</div>}
      </div>
    </button>
  );
}

function OverviewStatCard({ label, value, detail, tone = 'neutral', onClick }) {
  const toneMap = {
    neutral: { bg: 'rgba(255,255,255,0.92)', border: 'rgba(203,213,225,0.8)', value: 'var(--text-primary)' },
    amber: { bg: 'rgba(251,191,36,0.10)', border: 'rgba(251,191,36,0.35)', value: '#b45309' },
    emerald: { bg: 'rgba(16,185,129,0.10)', border: 'rgba(16,185,129,0.30)', value: '#047857' },
    blue: { bg: 'rgba(59,130,246,0.09)', border: 'rgba(96,165,250,0.28)', value: '#1d4ed8' },
    violet: { bg: 'rgba(139,92,246,0.09)', border: 'rgba(167,139,250,0.3)', value: '#6d28d9' },
    coral: { bg: 'rgba(239,68,68,0.08)', border: 'rgba(248,113,113,0.28)', value: '#dc2626' },
  };
  const palette = toneMap[tone] || toneMap.neutral;
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        borderRadius: 22,
        border: `1px solid ${palette.border}`,
        background: palette.bg,
        padding: '18px 18px 16px',
        textAlign: 'left',
        display: 'grid',
        gap: 8,
        cursor: onClick ? 'pointer' : 'default',
        boxShadow: '0 8px 20px rgba(15,23,42,0.04)',
      }}
    >
      <div style={{ fontSize: 11, fontWeight: 800, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>{label}</div>
      <div style={{ fontSize: 30, fontWeight: 900, lineHeight: 1, letterSpacing: '-0.04em', color: palette.value }}>{value}</div>
      {detail ? <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{detail}</div> : null}
    </button>
  );
}

function OverviewChartCard({ title, subtitle, action, children }) {
  return (
    <div
      style={{
        background: 'rgba(255,255,255,0.96)',
        border: '1px solid rgba(226,232,240,0.9)',
        borderRadius: 24,
        boxShadow: '0 14px 30px rgba(15,23,42,0.05)',
        padding: 20,
        display: 'grid',
        gap: 16,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: '-0.02em', color: '#0f172a' }}>{title}</div>
          {subtitle ? <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{subtitle}</div> : null}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

function ModernOverview({ sessions, inventory, buyerGroups, saleOrders, customers, reportRows, streamStatus, trackedUsernames, trackedAlerts, onTabChange }) {
  const [qrPreview, setQrPreview] = useState(null);
  const orders = saleOrders.rows || [];
  const activeOrders = orders.filter((row) => row.state !== 'cancel');
  const paidOrders = activeOrders.filter((row) => row.payment_status === 'paid');
  const pendingSaleOrders = (buyerGroups.rows || []).filter((row) => !row.sale_order_id).length;
  const lowStock = Number(inventory.low_stock_count || 0);
  const productCount = inventory.total_products ?? (inventory.rows || []).length ?? 0;
  const customerCount = (customers.rows || []).length;
  const revenue = activeOrders.reduce((sum, row) => sum + Number(row.amount_total || row.total_amount || 0), 0);
  const reportProfit = (reportRows.rows || []).reduce((sum, row) => sum + Number(row.total_profit || row.profit || 0), 0);
  const profit = reportProfit || activeOrders.reduce((sum, row) => sum + Number(row.profit || row.margin || 0), 0);
  const avgOrder = activeOrders.length ? revenue / activeOrders.length : 0;
  const paidRate = activeOrders.length ? Math.round((paidOrders.length / activeOrders.length) * 100) : 0;
  const cancelledCount = orders.filter((row) => row.state === 'cancel').length;
  const liveSession = (sessions || []).find((session) => session.status === 'live');
  const todayKey = new Date().toISOString().slice(0, 10);
  const todayOrders = activeOrders.filter((row) => {
    const dt = getSafeDate(row.date_order || row.ordered_at || row.created_at);
    return dt && dt.toISOString().slice(0, 10) === todayKey;
  });
  const todayRevenue = todayOrders.reduce((sum, row) => sum + Number(row.amount_total || row.total_amount || 0), 0);
  const tiktokHistory = (() => {
    try {
      return readStore().history || [];
    } catch {
      return [];
    }
  })();

  const channelMeta = {
    whatnot: { label: 'Whatnot', color: '#f59e0b', tab: 'orders-whatnot' },
    tiktok_live: { label: 'TikTok Live', color: '#7c3aed', tab: 'tiktok-live-sales' },
    tiktok_shop: { label: 'TikTok Shop', color: '#0ea5e9', tab: 'tiktok-shop-sales' },
    affiliate: { label: 'Partners', color: '#10b981', tab: 'orders-affiliate' },
    in_house: { label: 'In-House', color: '#64748b', tab: 'in-house-sales' },
  };
  const channelRows = useMemo(() => {
    const map = new Map();
    orders.forEach((row) => {
      const key = getOrderPlatformKey(row);
      if (!map.has(key)) {
        map.set(key, {
          key,
          label: channelMeta[key]?.label || key,
          color: channelMeta[key]?.color || '#64748b',
          tab: channelMeta[key]?.tab || 'orders',
          revenue: 0,
          orders: 0,
          cancelled: 0,
        });
      }
      const item = map.get(key);
      if (row.state === 'cancel') {
        item.cancelled += 1;
      } else {
        item.revenue += Number(row.amount_total || row.total_amount || 0);
        item.orders += 1;
      }
    });
    return [...map.values()].sort((a, b) => b.revenue - a.revenue);
  }, [orders]);

  const trendRows = useMemo(() => {
    const map = new Map();
    activeOrders.forEach((row) => {
      const dt = getSafeDate(row.date_order || row.ordered_at || row.created_at);
      if (!dt) return;
      const key = dt.toISOString().slice(0, 10);
      if (!map.has(key)) {
        map.set(key, {
          key,
          day: dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
          revenue: 0,
          orders: 0,
        });
      }
      const item = map.get(key);
      item.revenue += Number(row.amount_total || row.total_amount || 0);
      item.orders += 1;
    });
    return [...map.values()].sort((a, b) => a.key.localeCompare(b.key)).slice(-10);
  }, [activeOrders]);

  const recentOrders = useMemo(() => {
    return [...activeOrders]
      .map((row) => ({
        id: row.id,
        platform: channelMeta[getOrderPlatformKey(row)]?.label || getOrderPlatformKey(row),
        color: channelMeta[getOrderPlatformKey(row)]?.color || '#64748b',
        buyer: row.whatnot_buyer_username || row.partner_id_name || row.partner_name || 'Unknown buyer',
        amount: Number(row.amount_total || row.total_amount || 0),
        date: row.date_order || row.ordered_at || row.created_at,
      }))
      .sort((a, b) => (getSafeDate(b.date)?.getTime() || 0) - (getSafeDate(a.date)?.getTime() || 0))
      .slice(0, 7);
  }, [activeOrders]);

  const workItems = [
    {
      title: liveSession ? 'Live session running' : 'No live session active',
      detail: liveSession ? `${liveSession.name || `Session #${liveSession.id}`} is currently live.` : 'Start from Operator when the floor is ready.',
      tone: liveSession ? '#10b981' : '#64748b',
      action: 'Open Operator',
      onClick: () => { window.location.href = '/operator'; },
    },
    {
      title: `${pendingSaleOrders} pending sale orders`,
      detail: pendingSaleOrders ? 'Buyer groups still need sale orders created.' : 'No pending buyer groups.',
      tone: pendingSaleOrders ? '#f59e0b' : '#10b981',
      action: 'Open Sales',
      onClick: () => onTabChange('orders'),
    },
    {
      title: `${lowStock} low-stock products`,
      detail: lowStock ? 'Replenishment or product prep may be needed.' : 'Inventory risk looks calm.',
      tone: lowStock ? '#ef4444' : '#10b981',
      action: 'Open Inventory',
      onClick: () => onTabChange('inventory'),
    },
    {
      title: `${tiktokHistory.length} TikTok live sessions`,
      detail: 'Upload CSV, labels, and pull sheets from the TikTok Live Auctions page.',
      tone: '#7c3aed',
      action: 'Open Packing',
      onClick: () => onTabChange('tiktok-live-sales'),
    },
  ];

  const moneyCards = [
    { label: 'Revenue', value: fmt(revenue), sub: `${activeOrders.length} active orders`, color: '#6C47FF', tab: 'orders' },
    { label: 'Profit', value: fmt(profit), sub: `${revenue ? ((profit / revenue) * 100).toFixed(1) : '0.0'}% margin`, color: profit >= 0 ? '#0F9F6E' : '#DC2626', tab: 'finances' },
    { label: 'Avg Order', value: fmt(avgOrder), sub: `${paidRate}% paid rate`, color: '#1d4ed8', tab: 'orders' },
    { label: 'Customers', value: customerCount.toLocaleString(), sub: `${paidOrders.length} paid orders`, color: '#6C47FF', tab: 'customers' },
    { label: 'Low Stock', value: lowStock.toLocaleString(), sub: lowStock ? 'Needs replenishment' : 'Stock looks stable', color: lowStock ? '#D97706' : '#475569', tab: 'inventory' },
    { label: 'Live Sessions', value: liveSession ? '1' : '0', sub: liveSession ? (liveSession.name || `Session #${liveSession.id}`) : `${tiktokHistory.length} TikTok lives tracked`, color: liveSession ? '#0F9F6E' : '#475569', tab: liveSession ? 'sessions' : 'tiktok-live-sales' },
  ];
  const overviewSnapshot = [
    {
      label: 'System state',
      value: liveSession ? 'Live session active' : 'Ready for next live',
      detail: liveSession ? `${liveSession.total_products_sold || 0} sold · ${fmt(liveSession.total_revenue || 0)}` : `${cancelledCount} cancelled orders tracked`,
      tone: liveSession ? 'var(--accent-emerald)' : 'var(--text-secondary)',
    },
    {
      label: 'Pending sale orders',
      value: pendingSaleOrders.toLocaleString(),
      detail: pendingSaleOrders ? 'Buyer groups still need sale orders created' : 'No pending buyer groups',
      tone: pendingSaleOrders ? 'var(--accent-amber)' : 'var(--accent-emerald)',
    },
    {
      label: 'Inventory risk',
      value: lowStock.toLocaleString(),
      detail: lowStock ? 'Products at or below threshold' : 'No immediate stock pressure',
      tone: lowStock ? 'var(--accent-coral)' : 'var(--text-secondary)',
    },
    {
      label: 'Orders today',
      value: todayOrders.length.toLocaleString(),
      detail: `${fmt(todayRevenue)} processed today`,
      tone: 'var(--accent-primary)',
    },
  ];

  async function openSelfCheckoutQr() {
    try {
      const link = `${window.location.origin}/self-checkout`;
      const data = await fetchApi(`/api/qr_code?value=${encodeURIComponent(link)}`);
      setQrPreview({
        title: 'Self-Checkout',
        link,
        qrCodeDataUrl: data?.qr_code_data_url || '',
      });
    } catch {
      setQrPreview({
        title: 'Self-Checkout',
        link: `${window.location.origin}/self-checkout`,
        qrCodeDataUrl: '',
      });
    }
  }

  return (
    <div className="modern-overview">
      <section className="modern-overview-hero">
        <div className="modern-overview-hero-copy">
          <div className="modern-overview-kicker">YNF Deals Ops</div>
          <h2>Operations Overview</h2>
          <p>
            Real-time performance monitoring across live channels, orders, inventory pressure, and packing work.
          </p>
          <div className="modern-overview-actions">
            <Link to="/operator" className="modern-overview-primary">Live Command</Link>
            <button type="button" className="modern-overview-secondary" onClick={() => onTabChange('graphs')}>Analytics</button>
            <button type="button" className="modern-overview-secondary" onClick={() => onTabChange('inventory')}>Inventory</button>
            <button type="button" className="modern-overview-secondary" onClick={() => onTabChange('tiktok-live-sales')}>TikTok Packing</button>
            <button type="button" className="modern-overview-secondary" onClick={openSelfCheckoutQr}>Self-Checkout QR</button>
          </div>
        </div>
        <div className="modern-overview-status-card">
          <div className="modern-overview-status-header">
            <div>
              <div className="modern-overview-live-label">Operations Snapshot</div>
              <div className="modern-overview-status-title">{streamStatus?.running ? 'System online' : 'Command center ready'}</div>
            </div>
            <span className={`modern-overview-live-pill ${liveSession ? 'is-live' : ''}`}>{liveSession ? 'LIVE' : 'READY'}</span>
          </div>
          <div className="modern-overview-status-list">
            {overviewSnapshot.map((item) => (
              <div key={item.label} className="modern-overview-status-row">
                <div>
                  <div className="modern-overview-status-label">{item.label}</div>
                  <div className="modern-overview-status-detail">{item.detail}</div>
                </div>
                <strong style={{ color: item.tone }}>{item.value}</strong>
              </div>
            ))}
          </div>
        </div>
      </section>

      {qrPreview ? (
        <section className="modern-overview-panel" style={{ marginTop: 16 }}>
          <div className="modern-panel-head">
            <div>
              <h3>{qrPreview.title} QR</h3>
              <p>Open this on a staff screen and let customers scan it.</p>
            </div>
            <button type="button" onClick={() => setQrPreview(null)}>Close</button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 280px) minmax(0, 1fr)', gap: 18, alignItems: 'center' }}>
            <div style={{ display: 'grid', justifyItems: 'center' }}>
              {qrPreview.qrCodeDataUrl ? (
                <img src={qrPreview.qrCodeDataUrl} alt={`${qrPreview.title} QR`} style={{ width: '100%', maxWidth: 260, background: 'white', borderRadius: 24, padding: 12, border: '1px solid rgba(148,163,184,0.18)' }} />
              ) : (
                <div className="modern-empty-state">QR preview unavailable right now.</div>
              )}
            </div>
            <div style={{ display: 'grid', gap: 12 }}>
              <div style={{ fontSize: 13, color: '#64748b', lineHeight: 1.7 }}>
                Customers can scan this to open the mobile self-checkout lane without logging in.
              </div>
              <div style={{ fontSize: 12, color: '#475569', wordBreak: 'break-all', padding: 12, borderRadius: 16, background: 'rgba(248,250,252,0.96)', border: '1px solid rgba(148,163,184,0.16)' }}>
                {qrPreview.link}
              </div>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <button type="button" className="modern-overview-secondary" onClick={() => navigator.clipboard?.writeText(qrPreview.link)}>Copy Link</button>
                <Link to="/self-checkout" className="modern-overview-secondary">Open Self-Checkout</Link>
              </div>
            </div>
          </div>
        </section>
      ) : null}

      <section className="modern-overview-money-grid">
        {moneyCards.map((card) => (
          <button key={card.label} type="button" className="modern-money-card" onClick={() => onTabChange(card.tab)}>
            <span style={{ background: card.color }} />
            <div>{card.label}</div>
            <strong style={{ color: card.color }}>{card.value}</strong>
            <small>{card.sub}</small>
          </button>
        ))}
      </section>

      <section className="modern-overview-main-grid">
        <div className="modern-overview-panel modern-overview-panel-large">
          <div className="modern-panel-head">
            <div>
              <h3>Revenue Flow</h3>
              <p>Last 10 active selling days</p>
            </div>
            <button type="button" onClick={() => onTabChange('graphs')}>Charts</button>
          </div>
          {trendRows.length ? (
            <ResponsiveContainer width="100%" height={270}>
              <AreaChart data={trendRows} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="overviewRevenueGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.38} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.22)" />
                <XAxis dataKey="day" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} width={58} axisLine={false} tickLine={false} tickFormatter={(v) => `$${Math.round(v)}`} />
                <Tooltip formatter={(value, name) => [name === 'orders' ? value : fmt(value), name === 'orders' ? 'Orders' : 'Revenue']} />
                <Area type="monotone" dataKey="revenue" stroke="#6366f1" strokeWidth={3} fill="url(#overviewRevenueGradient)" />
                <Line type="monotone" dataKey="orders" stroke="#0ea5e9" strokeWidth={2} dot={{ r: 2 }} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="modern-empty-state">No revenue trend data yet.</div>
          )}
        </div>

        <div className="modern-overview-panel">
          <div className="modern-panel-head">
            <div>
              <h3>Work Queue</h3>
              <p>What needs attention</p>
            </div>
          </div>
          <div className="modern-work-list">
            {workItems.map((item) => (
              <button key={item.title} type="button" onClick={item.onClick} className="modern-work-item">
                <span style={{ background: item.tone }} />
                <div>
                  <strong>{item.title}</strong>
                  <small>{item.detail}</small>
                </div>
                <em>{item.action}</em>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="modern-overview-main-grid">
        <div className="modern-overview-panel">
          <div className="modern-panel-head">
            <div>
              <h3>Channel Mix</h3>
              <p>Where revenue is coming from</p>
            </div>
          </div>
          {channelRows.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={channelRows} layout="vertical" margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.22)" />
                <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={(v) => `$${Math.round(v)}`} />
                <YAxis type="category" dataKey="label" width={86} tick={{ fill: '#334155', fontSize: 11, fontWeight: 700 }} />
                <Tooltip formatter={(value) => fmt(value)} />
                <Bar dataKey="revenue" radius={[0, 8, 8, 0]}>
                  {channelRows.map((row) => <Cell key={row.key} fill={row.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="modern-empty-state">No channel sales yet.</div>
          )}
        </div>

        <div className="modern-overview-panel">
          <div className="modern-panel-head">
            <div>
              <h3>Recent Activity</h3>
              <p>Latest completed sales</p>
            </div>
            <button type="button" onClick={() => onTabChange('orders')}>Sales</button>
          </div>
          <div className="modern-activity-list">
            {recentOrders.length ? recentOrders.map((order) => (
              <div key={order.id} className="modern-activity-row">
                <span style={{ background: order.color }} />
                <div>
                  <strong>{order.buyer}</strong>
                  <small>{order.platform} · {companyFmtDt(order.date)}</small>
                </div>
                <b>{fmt(order.amount)}</b>
              </div>
            )) : <div className="modern-empty-state">No recent orders yet.</div>}
          </div>
        </div>
      </section>

      <section className="modern-overview-mini-grid">
        <div className="modern-mini-card" onClick={() => onTabChange('inventory')} role="button" tabIndex={0}>
          <Package2 size={20} />
          <div>
            <strong>{productCount}</strong>
            <span>Products</span>
          </div>
        </div>
        <div className="modern-mini-card" onClick={() => onTabChange('customers')} role="button" tabIndex={0}>
          <Users2 size={20} />
          <div>
            <strong>{customerCount}</strong>
            <span>Customers</span>
          </div>
        </div>
        <div className="modern-mini-card" onClick={() => onTabChange('orders')} role="button" tabIndex={0}>
          <Receipt size={20} />
          <div>
            <strong>{activeOrders.length}</strong>
            <span>Orders</span>
          </div>
        </div>
        <div className="modern-mini-card" onClick={() => onTabChange('tiktok-live-sales')} role="button" tabIndex={0}>
          <Sparkles size={20} />
          <div>
            <strong>{tiktokHistory.length}</strong>
            <span>TikTok Lives</span>
          </div>
        </div>
      </section>

      <TrackedBuyerPanel trackedUsernames={trackedUsernames} trackedAlerts={trackedAlerts} />
    </div>
  );
}

function AdminDashboard({ sessions, inventory, buyerGroups, saleOrders, customers, reportRows, streamStatus, trackedUsernames, trackedAlerts, onTabChange }) {
  const [intelligenceData, setIntelligenceData] = useState(null);
  const [megaData, setMegaData] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      Promise.all([
        fetchApi('/api/company/intelligence').catch(() => null),
        fetchApi('/api/company/mega_dashboard').catch(() => null),
      ]).then(([intelligencePayload, megaPayload]) => {
        if (cancelled) return;
        setIntelligenceData(intelligencePayload);
        setMegaData(megaPayload);
      });
    }, 1200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  const whatnotSessions = useMemo(
    () => [...(sessions || [])].filter((session) => !isTikTokSession(session)),
    [sessions],
  );
  const whatnotSessionIds = useMemo(
    () => new Set(whatnotSessions.map((session) => Number(session.id)).filter(Boolean)),
    [whatnotSessions],
  );
  const whatnotOrders = useMemo(
    () => (saleOrders.rows || []).filter((row) => getOrderPlatformKey(row) === 'whatnot'),
    [saleOrders.rows],
  );
  const whatnotReportRows = useMemo(
    () => (reportRows.rows || []).filter((row) => {
      if (row?.session_id && whatnotSessionIds.has(Number(row.session_id))) return true;
      const sessionName = String(row?.session_id_name || '').toLowerCase();
      return !sessionName.includes('tiktok');
    }),
    [reportRows.rows, whatnotSessionIds],
  );

  const completedOrders = useMemo(
    () => whatnotOrders.filter((row) => row.state !== 'cancel'),
    [whatnotOrders],
  );
  const paidOrders = useMemo(
    () => completedOrders.filter((row) => row.payment_status === 'paid'),
    [completedOrders],
  );
  const liveWhatnotSessions = useMemo(
    () => whatnotSessions.filter((session) => session.status === 'live'),
    [whatnotSessions],
  );
  const endedWhatnotSessions = useMemo(
    () => [...whatnotSessions]
      .filter((session) => (session.total_products_sold || 0) > 0)
      .sort((a, b) => (getSafeDate(b.ended_at || b.started_at || b.created_at)?.getTime() || 0) - (getSafeDate(a.ended_at || a.started_at || a.created_at)?.getTime() || 0)),
    [whatnotSessions],
  );

  const totalRevenue = completedOrders.reduce((sum, row) => sum + Number(row.amount_total || 0), 0);
  const totalProfit = whatnotReportRows.reduce((sum, row) => sum + Number(row.total_profit || 0), 0);
  const totalProductsSold = whatnotSessions.reduce((sum, session) => sum + Number(session.total_products_sold || 0), 0);
  const avgOrderValue = completedOrders.length ? totalRevenue / completedOrders.length : 0;
  const fulfilmentPending = completedOrders.filter((row) => row.fulfillment_status !== 'shipped').length;
  const cancelledOrders = whatnotOrders.filter((row) => row.state === 'cancel').length;
  const uniqueBuyers = new Set(
    completedOrders.map((row) => String(row.whatnot_buyer_username || row.partner_id_name || row.partner_name || '').trim().toLowerCase()).filter(Boolean),
  ).size;
  const currentLiveSession = liveWhatnotSessions[0] || null;

  const trendByDay = useMemo(() => {
    const map = new Map();
    completedOrders.forEach((row) => {
      const dt = getSafeDate(row.date_order);
      if (!dt) return;
      const key = dt.toISOString().slice(0, 10);
      if (!map.has(key)) {
        map.set(key, { key, day: dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), revenue: 0, orders: 0 });
      }
      const current = map.get(key);
      current.revenue += Number(row.amount_total || 0);
      current.orders += 1;
    });
    return [...map.values()].sort((a, b) => a.key.localeCompare(b.key)).slice(-14);
  }, [completedOrders]);

  const sessionPerformance = useMemo(() => {
    return endedWhatnotSessions.slice(0, 8).reverse().map((session) => ({
      name: String(session.name || `Session #${session.id}`).replace(/^Whatnot\s*/i, '').slice(0, 18),
      revenue: Number(session.total_revenue || 0),
      profit: Number(session.total_profit || 0),
      lots: Number(session.total_lots_sold || 0),
    }));
  }, [endedWhatnotSessions]);

  const orderMix = useMemo(() => {
    const shipped = completedOrders.filter((row) => row.fulfillment_status === 'shipped').length;
    const paid = completedOrders.filter((row) => row.payment_status === 'paid' && row.fulfillment_status !== 'shipped').length;
    const pending = completedOrders.filter((row) => row.payment_status !== 'paid').length;
    return [
      { name: 'Shipped', value: shipped, color: '#10b981' },
      { name: 'Paid', value: paid, color: '#3b82f6' },
      { name: 'Pending', value: pending, color: '#f59e0b' },
      { name: 'Cancelled', value: cancelledOrders, color: '#ef4444' },
    ].filter((item) => item.value > 0);
  }, [completedOrders, cancelledOrders]);

  const topBuyers = useMemo(() => {
    const map = new Map();
    completedOrders.forEach((row) => {
      const key = String(row.whatnot_buyer_username || row.partner_id_name || row.partner_name || 'Unknown').trim();
      if (!key) return;
      if (!map.has(key)) map.set(key, { name: key, revenue: 0, orders: 0 });
      const current = map.get(key);
      current.revenue += Number(row.amount_total || 0);
      current.orders += 1;
    });
    return [...map.values()].sort((a, b) => b.revenue - a.revenue).slice(0, 8);
  }, [completedOrders]);

  const topProducts = useMemo(() => {
    return [...whatnotReportRows]
      .sort((a, b) => Number(b.total_profit || 0) - Number(a.total_profit || 0))
      .slice(0, 8)
      .map((row) => ({
        name: row.product_name || 'Unknown',
        sold: row.times_sold || 0,
        revenue: row.total_revenue || 0,
        profit: row.total_profit || 0,
      }));
  }, [whatnotReportRows]);

  const recentSessions = endedWhatnotSessions.slice(0, 5);
  const productCount = inventory.total_products ?? (inventory.rows || []).length ?? 0;
  const totalLowStock = inventory.low_stock_count || 0;
  const paidRate = completedOrders.length ? Math.round((paidOrders.length / completedOrders.length) * 100) : 0;
  const intelligenceSummary = intelligenceData?.summary || {};
  const recommendations = intelligenceData?.recommendations || {};
  const megaTotals = megaData?.totals || {};
  const megaInventory = megaData?.inventory || {};
  const allCompletedOrders = useMemo(
    () => (saleOrders.rows || []).filter((row) => row.state !== 'cancel'),
    [saleOrders.rows],
  );
  const channelSummary = useMemo(() => {
    const labels = {
      whatnot: { label: 'Whatnot', tone: 'amber', tab: 'orders-whatnot', color: '#f59e0b' },
      tiktok_live: { label: 'TikTok Live', tone: 'violet', tab: 'tiktok-live-sales', color: '#8b5cf6' },
      tiktok_shop: { label: 'TikTok Shop', tone: 'blue', tab: 'tiktok-shop-sales', color: '#2563eb' },
      affiliate: { label: 'Partners', tone: 'emerald', tab: 'orders-affiliate', color: '#10b981' },
      in_house: { label: 'In-House', tone: 'neutral', tab: 'in-house-sales', color: '#64748b' },
    };
    const map = new Map();
    (saleOrders.rows || []).forEach((row) => {
      const key = getOrderPlatformKey(row);
      if (!map.has(key)) {
        map.set(key, {
          key,
          label: labels[key]?.label || key,
          tone: labels[key]?.tone || 'neutral',
          color: labels[key]?.color || '#64748b',
          tab: labels[key]?.tab || 'orders',
          revenue: 0,
          orders: 0,
          paid: 0,
          cancelled: 0,
        });
      }
      const current = map.get(key);
      if (row.state === 'cancel') {
        current.cancelled += 1;
      } else {
        current.revenue += Number(row.amount_total || 0);
        current.orders += 1;
        if (row.payment_status === 'paid') current.paid += 1;
      }
    });
    return [...map.values()].sort((a, b) => b.revenue - a.revenue);
  }, [saleOrders.rows]);
  const totalCompanyRevenue = channelSummary.reduce((sum, row) => sum + row.revenue, 0);
  const totalCompanyOrders = channelSummary.reduce((sum, row) => sum + row.orders, 0);
  const companyRevenueTrend = useMemo(() => {
    const map = new Map();
    (saleOrders.rows || []).forEach((row) => {
      if (row.state === 'cancel') return;
      const dt = getSafeDate(row.date_order);
      if (!dt) return;
      const key = dt.toISOString().slice(0, 10);
      if (!map.has(key)) {
        map.set(key, { key, day: dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), whatnot: 0, tiktok: 0, others: 0 });
      }
      const current = map.get(key);
      const platform = getOrderPlatformKey(row);
      if (platform === 'whatnot') current.whatnot += Number(row.amount_total || 0);
      else if (platform === 'tiktok_live' || platform === 'tiktok_shop') current.tiktok += Number(row.amount_total || 0);
      else current.others += Number(row.amount_total || 0);
    });
    return [...map.values()].sort((a, b) => a.key.localeCompare(b.key)).slice(-14);
  }, [saleOrders.rows]);
  const concentrationRows = useMemo(() => {
    if (!totalRevenue) return [];
    return topBuyers.slice(0, 5).map((buyer) => ({
      ...buyer,
      share: (buyer.revenue / totalRevenue) * 100,
    }));
  }, [topBuyers, totalRevenue]);
  const inventoryHealthRows = [
    { name: 'Low Stock', value: Number(megaInventory.low_stock_count || totalLowStock || 0), color: '#f59e0b' },
    { name: 'Out Of Stock', value: Number(megaInventory.out_of_stock_count || 0), color: '#ef4444' },
    { name: 'Missing Images', value: Number(megaInventory.missing_image_count || 0), color: '#06b6d4' },
    { name: 'Unverified', value: Number(megaInventory.unverified_notes_count || 0), color: '#8b5cf6' },
  ].filter((row) => row.value > 0);
  const operationsMetrics = [
    { label: 'Pending Sale Orders', value: (buyerGroups.rows || []).filter((row) => !row.sale_order_id).length, tone: 'amber', tab: 'orders' },
    { label: 'Unpaid Winners', value: Number(intelligenceSummary.unpaid_order_count || 0), tone: Number(intelligenceSummary.unpaid_order_count || 0) ? 'coral' : 'neutral', tab: 'orders-whatnot' },
    { label: 'Repeat Buyers', value: Number(intelligenceSummary.repeat_buyer_count || 0), tone: 'emerald', tab: 'customers' },
    { label: 'Avg Time To Buy', value: intelligenceSummary.avg_minutes_to_buy != null ? `${intelligenceSummary.avg_minutes_to_buy}m` : '—', tone: 'blue' },
  ];
  const megaMetrics = [
    { label: 'Units Sold', value: Number(megaTotals.units || 0), detail: 'All channels', tone: 'blue' },
    { label: 'Fees', value: fmt(Number(megaTotals.fees || 0)), detail: 'Tracked fees', tone: 'coral' },
    { label: 'Margin', value: `${Number(megaTotals.margin_pct || 0).toFixed(1)}%`, detail: 'Company-wide', tone: Number(megaTotals.margin_pct || 0) >= 20 ? 'emerald' : 'amber' },
    { label: 'Stock Value', value: fmt(Number(megaInventory.total_stock_value || inventory.total_stock_value || 0)), detail: 'Inventory carrying value', tone: 'violet', tab: 'inventory' },
  ];
  const dayStrategy = recommendations.best_day_to_go_live || '—';
  const startStrategy = recommendations.best_start_time_hour != null
    ? new Date(2000, 0, 1, Number(recommendations.best_start_time_hour || 0)).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    : '—';
  const buyerFrequencyRows = useMemo(() => {
    const oneTimers = topBuyers.filter((buyer) => buyer.orders === 1).length;
    const repeaters = topBuyers.filter((buyer) => buyer.orders > 1).length;
    return [
      { name: 'Repeat', value: repeaters, color: '#10b981' },
      { name: 'One-Time', value: oneTimers, color: '#94a3b8' },
    ].filter((row) => row.value > 0);
  }, [topBuyers]);
  const recentOrderFlow = useMemo(() => {
    return [...allCompletedOrders]
      .map((row) => ({
        id: row.id,
        platform: getOrderPlatformKey(row),
        buyer: row.whatnot_buyer_username || row.partner_id_name || row.partner_name || 'Unknown',
        amount: Number(row.amount_total || 0),
        date: row.date_order,
      }))
      .sort((a, b) => (getSafeDate(b.date)?.getTime() || 0) - (getSafeDate(a.date)?.getTime() || 0))
      .slice(0, 8);
  }, [allCompletedOrders]);

  return (
    <div style={{ display: 'grid', gap: 18 }}>
      <section
        style={{
          borderRadius: 28,
          border: '1px solid rgba(226,232,240,0.95)',
          background: 'linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.96))',
          boxShadow: '0 20px 40px rgba(15,23,42,0.06)',
          padding: 24,
          display: 'grid',
          gap: 18,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 20, flexWrap: 'wrap' }}>
          <div style={{ maxWidth: 760 }}>
            <div style={{ fontSize: 12, fontWeight: 800, color: '#64748b', letterSpacing: '0.14em', textTransform: 'uppercase' }}>Whatnot Revenue Intelligence</div>
            <div style={{ fontSize: 40, fontWeight: 900, letterSpacing: '-0.05em', color: '#0f172a', marginTop: 8 }}>
              Overview
            </div>
            <div style={{ fontSize: 15, color: '#64748b', lineHeight: 1.7, marginTop: 8 }}>
              Read overall Whatnot sales health, revenue performance, buyer concentration, and session profitability from one operating view.
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <button type="button" className="company-ghost-btn" onClick={() => onTabChange('orders-whatnot')}>Open Whatnot Orders</button>
            <button type="button" className="company-primary-btn" onClick={() => onTabChange('auction-results')}>Open Auction Results</button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(185px, 1fr))', gap: 12 }}>
          <OverviewStatCard label="Revenue" value={fmt(totalRevenue)} detail={`${completedOrders.length} completed orders`} tone="amber" onClick={() => onTabChange('orders-whatnot')} />
          <OverviewStatCard label="Profit" value={fmt(totalProfit)} detail={whatnotReportRows.length ? 'Derived from product P&L' : 'Awaiting report rows'} tone="emerald" onClick={() => onTabChange('finances')} />
          <OverviewStatCard label="Avg Order" value={fmt(avgOrderValue)} detail={`${paidRate}% paid rate`} tone="blue" onClick={() => onTabChange('orders-whatnot')} />
          <OverviewStatCard label="Customers" value={uniqueBuyers} detail="Unique Whatnot buyers" tone="violet" onClick={() => onTabChange('customers')} />
          <OverviewStatCard label="Products Sold" value={totalProductsSold} detail={`${productCount} in catalog`} tone="blue" onClick={() => onTabChange('inventory')} />
          <OverviewStatCard label="Cancelled" value={cancelledOrders} detail={`${fulfilmentPending} still pending fulfillment`} tone="coral" onClick={() => onTabChange('orders-whatnot')} />
        </div>
      </section>

      <section
        style={{
          borderRadius: 24,
          border: '1px solid rgba(226,232,240,0.9)',
          background: 'rgba(255,255,255,0.95)',
          boxShadow: '0 12px 26px rgba(15,23,42,0.04)',
          padding: 20,
          display: 'grid',
          gap: 16,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800, color: '#0f172a' }}>Channel Revenue Board</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
              Compare Whatnot, TikTok, partners, and in-house performance from the same operating view.
            </div>
          </div>
          <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#94a3b8', fontWeight: 800 }}>Company Revenue</div>
              <div style={{ fontSize: 24, fontWeight: 900, letterSpacing: '-0.03em', color: '#0f172a', marginTop: 4 }}>{fmt(totalCompanyRevenue)}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#94a3b8', fontWeight: 800 }}>Orders Across Channels</div>
              <div style={{ fontSize: 24, fontWeight: 900, letterSpacing: '-0.03em', color: '#0f172a', marginTop: 4 }}>{totalCompanyOrders}</div>
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
          {channelSummary.map((channel) => (
            <OverviewStatCard
              key={channel.key}
              label={channel.label}
              value={fmt(channel.revenue)}
              detail={`${channel.orders} orders · ${channel.cancelled} cancelled`}
              tone={channel.tone}
              onClick={() => onTabChange(channel.tab)}
            />
          ))}
        </div>
      </section>

      <div style={{ display: 'grid', gridTemplateColumns: '1.15fr 1fr', gap: 16 }}>
        <OverviewChartCard
          title="Revenue by Channel"
          subtitle="Cross-channel revenue and order volume comparison"
        >
          {channelSummary.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={channelSummary} margin={{ top: 8, right: 12, left: 0, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis dataKey="label" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <YAxis yAxisId="left" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} width={60} tickFormatter={(v) => `$${Math.round(v)}`} />
                <YAxis yAxisId="right" orientation="right" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} width={36} />
                <Tooltip formatter={(value, name) => [name === 'orders' ? value : fmt(value), name === 'orders' ? 'Orders' : 'Revenue']} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar yAxisId="left" dataKey="revenue" name="Revenue" fill="#f59e0b" radius={[5, 5, 0, 0]} />
                <Bar yAxisId="right" dataKey="orders" name="Orders" fill="#2563eb" radius={[5, 5, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No channel revenue data yet.</div>
          )}
        </OverviewChartCard>

        <OverviewChartCard
          title="Company Revenue Trend"
          subtitle="Whatnot vs TikTok vs other revenue over time"
        >
          {companyRevenueTrend.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={companyRevenueTrend} margin={{ top: 8, right: 12, left: 0, bottom: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis dataKey="day" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} width={60} tickFormatter={(v) => `$${Math.round(v)}`} />
                <Tooltip formatter={(value) => fmt(value)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="whatnot" name="Whatnot" stroke="#f59e0b" strokeWidth={3} dot={{ r: 2 }} />
                <Line type="monotone" dataKey="tiktok" name="TikTok" stroke="#8b5cf6" strokeWidth={3} dot={{ r: 2 }} />
                <Line type="monotone" dataKey="others" name="Other" stroke="#64748b" strokeWidth={2} dot={{ r: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No cross-channel trend data available yet.</div>
          )}
        </OverviewChartCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16 }}>
        <OverviewChartCard
          title="Order State Mix"
          subtitle="How your current Whatnot order book is split right now"
        >
          {orderMix.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie data={orderMix} dataKey="value" nameKey="name" innerRadius={58} outerRadius={92} paddingAngle={2}>
                  {orderMix.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
                </Pie>
                <Tooltip formatter={(value, name) => [value, name]} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No Whatnot order mix to chart yet.</div>
          )}
        </OverviewChartCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.15fr 1fr', gap: 16 }}>
        <OverviewChartCard
          title="Sales Velocity"
          subtitle="Daily Whatnot order revenue across the latest selling window"
        >
          {trendByDay.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={trendByDay} margin={{ top: 6, right: 12, left: 0, bottom: 20 }}>
                <defs>
                  <linearGradient id="whatnotRevenueFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#60a5fa" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#60a5fa" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis dataKey="day" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <YAxis yAxisId="left" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} width={60} tickFormatter={(v) => `$${Math.round(v)}`} />
                <YAxis yAxisId="right" orientation="right" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} width={36} />
                <Tooltip formatter={(value, name) => [name === 'orders' ? value : fmt(value), name === 'orders' ? 'Orders' : 'Revenue']} />
                <Area yAxisId="left" type="monotone" dataKey="revenue" stroke="#2563eb" fill="url(#whatnotRevenueFill)" strokeWidth={3} />
                <Line yAxisId="right" type="monotone" dataKey="orders" stroke="#8b5cf6" strokeWidth={2} dot={{ r: 3 }} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No recent Whatnot order trend available yet.</div>
          )}
        </OverviewChartCard>

        <OverviewChartCard
          title="Top Buyers"
          subtitle="Highest-spending Whatnot customers in the current dataset"
          action={<button type="button" className="company-ghost-btn" onClick={() => onTabChange('customers')}>All Customers</button>}
        >
          {topBuyers.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={topBuyers} layout="vertical" margin={{ top: 6, right: 12, left: 10, bottom: 6 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" horizontal={false} />
                <XAxis type="number" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} tickFormatter={(v) => `$${Math.round(v)}`} />
                <YAxis type="category" dataKey="name" width={120} tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <Tooltip formatter={(value) => fmt(value)} />
                <Bar dataKey="revenue" fill="#7c3aed" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No buyer revenue distribution available yet.</div>
          )}
        </OverviewChartCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <OverviewChartCard
          title="Operations Metrics"
          subtitle="Pipeline, buyer quality, and response speed"
        >
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 12 }}>
            {operationsMetrics.map((metric) => (
              <OverviewStatCard
                key={metric.label}
                label={metric.label}
                value={metric.value}
                tone={metric.tone}
                onClick={metric.tab ? () => onTabChange(metric.tab) : undefined}
              />
            ))}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 12, marginTop: 12 }}>
            {megaMetrics.map((metric) => (
              <OverviewStatCard
                key={metric.label}
                label={metric.label}
                value={metric.value}
                detail={metric.detail}
                tone={metric.tone}
                onClick={metric.tab ? () => onTabChange(metric.tab) : undefined}
              />
            ))}
          </div>
        </OverviewChartCard>

        <OverviewChartCard
          title="Go Live Strategy"
          subtitle="Pulled from your company intelligence models"
          action={<button type="button" className="company-ghost-btn" onClick={() => onTabChange('intelligence')}>Open Intelligence</button>}
        >
          <div style={{ display: 'grid', gap: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <OverviewStatCard label="Best Day" value={dayStrategy} detail="Suggested go-live day" tone="amber" />
              <OverviewStatCard label="Best Start" value={startStrategy} detail="Suggested start time" tone="blue" />
            </div>
            <div style={{ padding: '14px 16px', borderRadius: 18, border: '1px solid rgba(16,185,129,0.18)', background: 'rgba(16,185,129,0.05)' }}>
              <div style={{ fontSize: 12, fontWeight: 800, color: '#047857', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Expected Revenue Window</div>
              <div style={{ fontSize: 22, fontWeight: 900, letterSpacing: '-0.03em', color: '#0f172a', marginTop: 6 }}>
                {fmt(recommendations.expected_revenue_low)} - {fmt(recommendations.expected_revenue_high)}
              </div>
              <div style={{ fontSize: 12, color: '#64748b', marginTop: 6 }}>
                Based on prior session performance, timing, and buyer behavior.
              </div>
            </div>
            {(recommendations.best_product_sequence_strategy || []).length ? (
              <div style={{ display: 'grid', gap: 8 }}>
                {(recommendations.best_product_sequence_strategy || []).slice(0, 4).map((item, index) => (
                  <div key={`${item}-${index}`} style={{ padding: '12px 14px', borderRadius: 14, border: '1px solid rgba(226,232,240,0.9)', background: 'rgba(248,250,252,0.82)', fontSize: 13, color: '#475569' }}>
                    {item}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </OverviewChartCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <OverviewChartCard
          title="Top Products by Profit"
          subtitle="Best performing Whatnot products from report rows"
          action={<button type="button" className="company-ghost-btn" onClick={() => onTabChange('finances')}>Open Reports</button>}
        >
          {topProducts.length ? (
            <div style={{ display: 'grid', gap: 10 }}>
              {topProducts.map((product, index) => (
                <div key={`${product.name}-${index}`} style={{ display: 'grid', gridTemplateColumns: '32px minmax(0,1fr) auto auto', gap: 12, alignItems: 'center', padding: '12px 14px', borderRadius: 16, border: '1px solid rgba(226,232,240,0.9)', background: 'rgba(248,250,252,0.82)' }}>
                  <div style={{ width: 32, height: 32, borderRadius: 999, background: 'rgba(59,130,246,0.08)', color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 800 }}>{index + 1}</div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 800, color: '#0f172a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{product.name}</div>
                    <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{product.sold} sold · Revenue {fmt(product.revenue)}</div>
                  </div>
                  <div style={{ fontSize: 12, color: '#64748b' }}>Profit</div>
                  <div style={{ fontSize: 15, fontWeight: 900, color: companyClrProfit(product.profit) }}>{fmt(product.profit)}</div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No Whatnot product profit rows available yet.</div>
          )}
        </OverviewChartCard>

        <OverviewChartCard
          title="Buyer Concentration"
          subtitle="See whether revenue is broad-based or dominated by a few buyers"
        >
          {concentrationRows.length ? (
            <div style={{ display: 'grid', gap: 10 }}>
              {concentrationRows.map((buyer, index) => (
                <div key={`${buyer.name}-${index}`} style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto', gap: 12, alignItems: 'center' }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                      <div style={{ fontSize: 13, fontWeight: 800, color: '#0f172a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{buyer.name}</div>
                      <div style={{ fontSize: 12, color: '#64748b' }}>{buyer.orders} orders</div>
                    </div>
                    <div style={{ marginTop: 6, height: 8, borderRadius: 999, background: 'rgba(226,232,240,0.8)', overflow: 'hidden' }}>
                      <div style={{ width: `${Math.min(100, buyer.share)}%`, height: '100%', borderRadius: 999, background: 'linear-gradient(90deg, #8b5cf6, #3b82f6)' }} />
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 13, fontWeight: 800, color: '#0f172a' }}>{fmt(buyer.revenue)}</div>
                    <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>{buyer.share.toFixed(1)}%</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Not enough buyer revenue data yet.</div>
          )}
        </OverviewChartCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <OverviewChartCard
          title="Inventory Risk Radar"
          subtitle="The inventory problems most likely to hurt sales flow"
        >
          {inventoryHealthRows.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={inventoryHealthRows} margin={{ top: 8, right: 12, left: 0, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} width={42} />
                <Tooltip formatter={(value) => [value, 'Count']} />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {inventoryHealthRows.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No inventory risk flags detected right now.</div>
          )}
        </OverviewChartCard>

        <OverviewChartCard
          title="Buyer Frequency"
          subtitle="How much of your top-buyer set is repeat vs one-time"
        >
          {buyerFrequencyRows.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={buyerFrequencyRows} dataKey="value" nameKey="name" innerRadius={54} outerRadius={90}>
                  {buyerFrequencyRows.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
                </Pie>
                <Tooltip formatter={(value, name) => [value, name]} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No buyer frequency split available yet.</div>
          )}
        </OverviewChartCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16 }}>
        <OverviewChartCard
          title="Operations Watchlist"
          subtitle="Live context, inventory exposure, and next actions"
        >
          <div style={{ display: 'grid', gap: 12 }}>
            <div style={{ display: 'grid', gap: 6, padding: '14px 16px', borderRadius: 18, border: '1px solid rgba(16,185,129,0.18)', background: 'rgba(16,185,129,0.05)' }}>
              <div style={{ fontSize: 12, fontWeight: 800, color: '#047857', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Current Live Signal</div>
              <div style={{ fontSize: 16, fontWeight: 800, color: '#0f172a' }}>{currentLiveSession ? currentLiveSession.name || `Session #${currentLiveSession.id}` : 'No active Whatnot live right now'}</div>
              <div style={{ fontSize: 12, color: '#64748b' }}>
                {currentLiveSession ? `${currentLiveSession.total_products_sold || 0} sold · ${fmt(currentLiveSession.total_revenue || 0)} revenue` : 'Use this view to monitor ended sessions and overall sales performance.'}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <OverviewStatCard label="Live Sessions" value={liveWhatnotSessions.length} detail={`${recentSessions.length} recent selling sessions`} tone="emerald" onClick={() => onTabChange('sessions')} />
              <OverviewStatCard label="Low Stock" value={totalLowStock} detail="Products at or below threshold" tone={totalLowStock ? 'coral' : 'neutral'} onClick={() => onTabChange('inventory')} />
            </div>

            <div style={{ display: 'grid', gap: 8 }}>
              {recentSessions.map((session) => (
                <button
                  key={session.id}
                  type="button"
                  onClick={() => onTabChange('sessions')}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'minmax(0,1fr) auto',
                    gap: 12,
                    alignItems: 'center',
                    textAlign: 'left',
                    padding: '12px 14px',
                    borderRadius: 16,
                    border: '1px solid rgba(226,232,240,0.9)',
                    background: 'rgba(255,255,255,0.84)',
                    cursor: 'pointer',
                  }}
                >
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 800, color: '#0f172a' }}>{session.name || `Session #${session.id}`}</div>
                    <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{session.total_products_sold || 0} sold · {session.total_lots_sold || 0} lots</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 13, fontWeight: 800, color: '#d97706' }}>{fmt(session.total_revenue || 0)}</div>
                    <div style={{ fontSize: 12, color: companyClrProfit(session.total_profit || 0), marginTop: 4 }}>{fmt(session.total_profit || 0)}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </OverviewChartCard>
      </div>

      <OverviewChartCard
        title="Recent Order Feed"
        subtitle="Most recent completed sales across channels"
        action={<button type="button" className="company-ghost-btn" onClick={() => onTabChange('orders')}>Open Sales Center</button>}
      >
        <div style={{ display: 'grid', gap: 8 }}>
          {recentOrderFlow.length ? recentOrderFlow.map((row) => (
            <div key={row.id} style={{ display: 'grid', gridTemplateColumns: '110px minmax(0,1fr) auto auto', gap: 12, alignItems: 'center', padding: '12px 14px', borderRadius: 16, border: '1px solid rgba(226,232,240,0.9)', background: 'rgba(255,255,255,0.82)' }}>
              <div style={{ fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.12em', color: row.platform === 'whatnot' ? '#d97706' : row.platform.startsWith('tiktok') ? '#7c3aed' : '#64748b' }}>
                {row.platform.replace('_', ' ')}
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 800, color: '#0f172a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.buyer}</div>
                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{companyFmtDt(row.date)}</div>
              </div>
              <div style={{ fontSize: 12, color: '#64748b' }}>Amount</div>
              <div style={{ fontSize: 14, fontWeight: 900, color: '#0f172a' }}>{fmt(row.amount)}</div>
            </div>
          )) : (
            <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No recent completed orders to show.</div>
          )}
        </div>
      </OverviewChartCard>

      <TrackedBuyerPanel trackedUsernames={trackedUsernames} trackedAlerts={trackedAlerts} />
    </div>
  );
}

function TrackedBuyerPanel({ trackedUsernames = [], trackedAlerts = [] }) {
  if (!trackedUsernames.length && !trackedAlerts.length) return null;

  return (
    <Panel title="Tracked Buyers">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '4px 0' }}>
        {trackedUsernames.length > 0 ? (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {trackedUsernames.map((username) => (
              <span
                key={username}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '6px 10px',
                  borderRadius: 999,
                  background: 'rgba(59,130,246,0.12)',
                  border: '1px solid rgba(59,130,246,0.24)',
                  color: 'var(--accent-blue)',
                  fontSize: 12,
                  fontWeight: 700,
                }}
              >
                @{username}
              </span>
            ))}
          </div>
        ) : null}

        {trackedAlerts.length === 0 ? (
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            No tracked buyer activity detected yet.
          </div>
        ) : (
          trackedAlerts.map((alert, index) => {
            const latestChat = alert.latest_chat;
            const latestBid = alert.latest_bid;
            const latestWin = alert.latest_win;
            return (
              <div
                key={`${alert.username}-${index}`}
                style={{
                  border: '1px solid rgba(59,130,246,0.18)',
                  borderRadius: 14,
                  padding: '12px 14px',
                  background: 'rgba(59,130,246,0.05)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ fontWeight: 800, fontSize: 14 }}>@{alert.username}</div>
                    <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)' }}>
                      {(alert.streams || []).join(', ') || 'Tracked spectator streams'}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', fontSize: 12, color: 'var(--text-secondary)' }}>
                    <div>{alert.chat_messages || 0} chat</div>
                    <div>{alert.bids || 0} bids</div>
                    <div>{alert.wins || 0} wins</div>
                  </div>
                </div>

                {latestChat ? (
                  <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-secondary)' }}>
                    Latest chat in <strong style={{ color: 'var(--text-primary)' }}>{latestChat.streamer_name || 'stream'}</strong>: {latestChat.message || '—'}
                  </div>
                ) : null}
                {latestBid ? (
                  <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
                    Latest bid in <strong style={{ color: 'var(--text-primary)' }}>{latestBid.streamer_name || 'stream'}</strong>: {latestBid.raw_amount || latestBid.amount || '—'}{latestBid.lot_number ? ` · Lot ${latestBid.lot_number}` : ''}
                  </div>
                ) : null}
                {latestWin ? (
                  <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
                    Latest win in <strong style={{ color: 'var(--text-primary)' }}>{latestWin.streamer_name || 'stream'}</strong>: {latestWin.price || '—'}{latestWin.lot_number ? ` · Lot ${latestWin.lot_number}` : ''}
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </Panel>
  );
}

function Overview({ sessions, inventory, buyerGroups, saleOrders, customers, reportRows, streamStatus, trackedUsernames, trackedAlerts, onTabChange }) {
  const liveSession = sessions.find((session) => session.status === 'live');
  const soldSessions = sessions.filter((session) => (session.total_products_sold || 0) > 0);
  const recentSessions = soldSessions.slice(0, 6);
  const pendingSaleOrders = (buyerGroups.rows || []).filter((row) => !row.sale_order_id).length;
  const lowStock = inventory.low_stock_count || 0;
  const bookedRevenue = saleOrders.confirmed_amount || 0;
  const quotePipeline = saleOrders.draft_amount || 0;
  const confirmedOrders = saleOrders.confirmed_count || 0;
  const quoteCount = saleOrders.draft_count || 0;
  const cancelledOrders = saleOrders.cancel_count || 0;
  const productCount = inventory.total_products ?? (inventory.rows || []).length ?? 0;
  const totalRevenue = (reportRows.rows || []).reduce((sum, row) => sum + (row.total_revenue || 0), 0);
  const totalProfit = (reportRows.rows || []).reduce((sum, row) => sum + (row.total_profit || 0), 0);
  const customerCount = (customers.rows || []).length;

  const notices = [
    pendingSaleOrders > 0 ? { key: 'orders', text: `${pendingSaleOrders} buyer order${pendingSaleOrders === 1 ? '' : 's'} pending sale order creation`, color: 'var(--accent-amber)', border: 'rgba(245,158,11,0.2)', bg: 'rgba(245,158,11,0.06)', tab: 'orders' } : null,
    lowStock > 0 ? { key: 'stock', text: `${lowStock} product${lowStock === 1 ? '' : 's'} at or below low-stock threshold`, color: 'var(--accent-coral)', border: 'rgba(239,68,68,0.2)', bg: 'rgba(239,68,68,0.06)', tab: 'inventory' } : null,
  ].filter(Boolean);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Session status bar */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: 14,
        padding: '14px 18px',
        background: 'linear-gradient(180deg, var(--bg-panel) 0%, var(--bg-elevated) 100%)',
        border: '1px solid var(--border-default)',
        borderLeft: `3px solid ${streamStatus?.running ? 'var(--accent-emerald)' : 'var(--border-strong)'}`,
        borderRadius: 10,
        boxShadow: 'var(--shadow-panel)',
        flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <StatusPill status={streamStatus?.running ? 'live' : 'ended'} />
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>
              {streamStatus?.running ? 'Live — stream is active' : liveSession ? liveSession.name || `Session #${liveSession.id}` : 'No active session'}
            </div>
            {liveSession && (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                Revenue {fmtK(liveSession.total_revenue)} · Profit {fmtK(liveSession.total_profit)} · {liveSession.total_products_sold || 0} sold
              </div>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Link to="/operator" className="btn-3d btn-3d-primary">
            Operator
          </Link>
          <button type="button" onClick={() => onTabChange('sessions')} className="btn-3d btn-3d-ghost">
            Sessions
          </button>
        </div>
      </div>

      {/* Notices */}
      {notices.map((n) => (
        <button key={n.key} type="button" onClick={() => onTabChange(n.tab)}
          style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', borderRadius: 10, background: n.bg, border: `1px solid ${n.border}`, color: n.color, fontSize: 13, fontWeight: 500, cursor: 'pointer', textAlign: 'left' }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor', flexShrink: 0 }} />
          {n.text}
        </button>
      ))}

      {/* Primary KPI strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
        <KpiCard label="Booked Revenue" value={fmtK(bookedRevenue)} color="var(--accent-amber)" onClick={() => onTabChange('orders')} />
        <KpiCard label="Total Profit" value={fmtK(totalProfit)} color={totalProfit > 0 ? 'var(--accent-emerald)' : 'var(--text-secondary)'} onClick={() => onTabChange('finances')} />
        <KpiCard label="Confirmed Orders" value={confirmedOrders} color="var(--accent-emerald)" onClick={() => onTabChange('orders')} />
        <KpiCard label="Stock Value" value={fmtK(inventory.total_stock_value)} color="var(--accent-amber)" onClick={() => onTabChange('inventory')} />
        <KpiCard label="Products" value={productCount} onClick={() => onTabChange('inventory')} />
        <KpiCard label="Customers" value={customerCount} onClick={() => onTabChange('customers')} />
      </div>

      {/* Two-column detail panels */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 14 }}>

        {/* Sales pipeline */}
        <Panel title="Sales Pipeline">
          <MetricRow label="Confirmed orders" value={confirmedOrders} valueColor="var(--accent-emerald)" onClick={() => onTabChange('orders')} />
          <MetricRow label="Booked revenue" value={fmtK(bookedRevenue)} valueColor="var(--accent-amber)" onClick={() => onTabChange('orders')} />
          <MetricRow label="Quote pipeline" value={fmtK(quotePipeline)} sub={`${quoteCount} draft`} onClick={() => onTabChange('orders')} />
          <MetricRow label="Pending SO creation" value={pendingSaleOrders} valueColor={pendingSaleOrders > 0 ? 'var(--accent-amber)' : undefined} onClick={() => onTabChange('orders')} />
          <MetricRow label="Cancelled orders" value={cancelledOrders} valueColor={cancelledOrders > 0 ? 'var(--accent-coral)' : undefined} onClick={() => onTabChange('orders')} last />
        </Panel>

        {/* Inventory + performance */}
        <Panel title="Inventory & Performance">
          <MetricRow label="Products in catalog" value={productCount} onClick={() => onTabChange('inventory')} />
          <MetricRow label="Stock value" value={fmtK(inventory.total_stock_value)} valueColor="var(--accent-amber)" onClick={() => onTabChange('inventory')} />
          <MetricRow label="Low stock alerts" value={lowStock} valueColor={lowStock > 0 ? 'var(--accent-coral)' : undefined} onClick={() => onTabChange('inventory')} />
          <MetricRow label="Top-line revenue" value={fmtK(totalRevenue)} valueColor="var(--accent-amber)" onClick={() => onTabChange('finances')} />
          <MetricRow label="Top-line profit" value={fmtK(totalProfit)} valueColor={totalProfit > 0 ? 'var(--accent-emerald)' : 'var(--accent-coral)'} onClick={() => onTabChange('finances')} last />
        </Panel>
      </div>

      <TrackedBuyerPanel trackedUsernames={trackedUsernames} trackedAlerts={trackedAlerts} />

      {/* Recent sessions */}
      <Panel
        title="Recent Sessions"
        action={
          <button type="button" onClick={() => onTabChange('sessions')}
            style={{ background: 'none', border: 'none', color: '#fbbf24', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>
            View all
          </button>
        }
      >
        {recentSessions.length === 0 ? (
          <div style={{ color: 'var(--text-secondary)', fontSize: 13, padding: '4px 0' }}>No sold sessions yet.</div>
        ) : (
          recentSessions.map((session, index) => (
            <button
              key={session.id}
              type="button"
              onClick={() => onTabChange('sessions')}
              style={{
                display: 'grid',
                gridTemplateColumns: 'auto minmax(0,1fr) auto auto auto',
                gap: 16,
                alignItems: 'center',
                width: '100%',
                background: 'transparent',
                border: 'none',
                borderTop: index === 0 ? 'none' : '1px solid var(--border-subtle)',
                padding: '11px 0',
                cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              <StatusPill status={session.status} />
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{session.name || `Session #${session.id}`}</div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                  {session.start_time ? new Date(session.start_time).toLocaleDateString() : 'No date'}
                  {' · '}{session.total_products_sold || 0} sold
                </div>
              </div>
              <div style={{ textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700, fontSize: 14 }}>{fmtK(session.total_revenue)}</div>
              <div style={{ textAlign: 'right', color: tone(session.total_profit, 0, 0), fontWeight: 700, fontSize: 14 }}>{fmtK(session.total_profit)}</div>
              <div style={{ textAlign: 'right', color: 'var(--text-secondary)', fontSize: 12 }}>{session.total_lots_sold || 0} lots</div>
            </button>
          ))
        )}
      </Panel>
    </div>
  );
}

function SessionsTab({ sessions, onSessionClick }) {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');

  const filtered = useMemo(() => (
    sessions.filter((session) => {
      const matchesSearch = !search || (session.name || '').toLowerCase().includes(search.toLowerCase());
      const matchesStatus = !status || session.status === status;
      return matchesSearch && matchesStatus;
    })
  ), [search, sessions, status]);

  const totals = filtered.reduce((acc, session) => {
    acc.products += session.total_products_sold || 0;
    acc.lots += session.total_lots_sold || 0;
    return acc;
  }, { products: 0, lots: 0 });
  const endedCount = filtered.filter((session) => session.status === 'ended').length;
  const liveCount = filtered.filter((session) => session.status === 'live').length;
  const draftCount = filtered.filter((session) => session.status === 'draft').length;
  const soldCount = filtered.filter((session) => (session.total_products_sold || 0) > 0).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
        <KpiCard label="Sessions" value={filtered.length} />
        <KpiCard label="Sold Sessions" value={soldCount} />
        <KpiCard label="Live" value={liveCount} color="var(--accent-emerald)" />
        <KpiCard label="Ended" value={endedCount} />
        <KpiCard label="Draft" value={draftCount} color="var(--accent-amber)" />
        <KpiCard label="Products Sold" value={totals.products} />
        <KpiCard label="Lots Sold" value={totals.lots} />
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <input
          type="text"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search sessions..."
          style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '6px 10px', fontSize: 12, minHeight: 34, lineHeight: 1.2, minWidth: 240, flex: 1 }}
        />
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '6px 30px 6px 10px', fontSize: 12, minHeight: 34, lineHeight: 1.2 }}
        >
          <option value="">All statuses</option>
          <option value="live">Live</option>
          <option value="draft">Draft</option>
          <option value="ended">Ended</option>
        </select>
      </div>

      <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)', overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-default)' }}>
                {['Status', 'Session', 'Start', 'Products', 'Lots', ''].map((heading, index) => (
                  <th
                    key={heading || 'action'}
                    style={{
                      padding: '11px 16px',
                      textAlign: index < 3 ? 'left' : 'right',
                      color: 'var(--text-secondary)',
                      fontWeight: 700,
                      fontSize: 11,
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ padding: 28, textAlign: 'center', color: 'var(--text-secondary)' }}>
                    No sessions found.
                  </td>
                </tr>
              ) : filtered.map((session) => {
                return (
                  <tr
                    key={session.id}
                    style={{ borderTop: '1px solid var(--border-subtle)', cursor: 'pointer' }}
                    onClick={() => onSessionClick && onSessionClick(session.id)}
                  >
                    <td style={{ padding: '12px 16px' }}><StatusPill status={session.status} /></td>
                    <td style={{ padding: '12px 16px', fontWeight: 700 }}>{session.name || `Session #${session.id}`}</td>
                    <td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                      {session.start_time ? new Date(session.start_time).toLocaleString() : '—'}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right', color: 'var(--text-secondary)' }}>{session.total_products_sold || 0}</td>
                    <td style={{ padding: '12px 16px', textAlign: 'right', color: 'var(--text-secondary)' }}>{session.total_lots_sold || 0}</td>
                    <td style={{ padding: '12px 16px', textAlign: 'right', color: 'var(--text-secondary)', fontSize: 11 }}>View →</td>
                  </tr>
                );
              })}
            </tbody>
            {filtered.length > 0 ? (
              <tfoot>
                <tr style={{ borderTop: '2px solid var(--border-default)', background: 'rgba(245,158,11,0.08)' }}>
                  <td colSpan={3} style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontWeight: 800, fontSize: 11, letterSpacing: '0.08em' }}>TOTALS</td>
                  <td style={{ padding: '12px 16px', textAlign: 'right', color: 'var(--text-secondary)', fontWeight: 800 }}>{totals.products}</td>
                  <td style={{ padding: '12px 16px', textAlign: 'right', color: 'var(--text-secondary)', fontWeight: 800 }}>{totals.lots}</td>
                  <td />
                </tr>
              </tfoot>
            ) : null}
          </table>
        </div>
      </div>

      <Panel title="Live Activity">
        <LiveFeed sessions={sessions} />
      </Panel>
    </div>
  );
}

function CompanyLazyFallback({ label = 'Loading workspace...' }) {
  return (
    <Panel title="Loading">
      <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{label}</div>
    </Panel>
  );
}

export default function Company() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get('tab');
  const storedTab = (() => {
    if (typeof window === 'undefined') return '';
    try {
      return window.localStorage.getItem(LAST_COMPANY_TAB_KEY) || '';
    } catch {
      return '';
    }
  })();
  const rawTab = requestedTab || storedTab || 'overview';
  const redirectedTab = TAB_REDIRECTS[rawTab] || rawTab;
  const cachedSessions = getCachedApi(COMPANY_SESSIONS_PATH, { sessions: [] });
  const cachedBuyerGroups = getCachedApi(COMPANY_BUYER_GROUPS_PATH, { rows: [] });
  const cachedSaleOrders = getCachedApi(COMPANY_SALE_ORDERS_OVERVIEW_PATH, { rows: [] });
  const cachedInventory = getCachedApi(COMPANY_INVENTORY_OVERVIEW_PATH, { rows: [] });
  const cachedInventoryCategories = getCachedApi('/api/inventory/categories', { rows: [] });
  const inventoryAllCacheKey = '/api/inventory?low_stock=3&active=all&pricing_schema=2';
  const cachedInventoryAll = getCachedApi(inventoryAllCacheKey, null);
  const cachedCustomers = getCachedApi(COMPANY_CUSTOMERS_OVERVIEW_PATH, { rows: [] });
  const cachedReportRows = getCachedApi(COMPANY_REPORTS_OVERVIEW_PATH, { rows: [] });
  const [authUser, setAuthUser] = useState(null);
  const [authLoaded, setAuthLoaded] = useState(false);
  const viewerRole = String(authUser?.role || 'admin').toLowerCase() === 'admin' ? 'admin' : 'staff';
  const roleRule = ROLE_NAV_RULES[viewerRole] || ROLE_NAV_RULES.staff;
  const allowedTabs = useMemo(() => (roleRule.tabs ? new Set(roleRule.tabs) : null), [roleRule]);
  const resolvedUrlTab = !requestedTab && !storedTab && viewerRole !== 'admin'
    ? roleRule.defaultTab
    : (allowedTabs && !allowedTabs.has(redirectedTab) ? roleRule.defaultTab : redirectedTab);
  const [activeTab, setActiveTabState] = useState(resolvedUrlTab);

  useEffect(() => {
    setActiveTabState(resolvedUrlTab);
    try {
      window.localStorage.setItem(LAST_COMPANY_TAB_KEY, resolvedUrlTab);
    } catch {
      // ignore storage failures
    }
  }, [resolvedUrlTab]);

  function writeTabToUrl(tab, options = {}) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set('tab', tab);
      return next;
    }, options);
  }

  function setActiveTab(tab) {
    const nextTab = allowedTabs && !allowedTabs.has(tab) ? roleRule.defaultTab : tab;
    setActiveTabState(nextTab);
    try {
      window.localStorage.setItem(LAST_COMPANY_TAB_KEY, nextTab);
    } catch {
      // ignore storage failures
    }
    writeTabToUrl(nextTab, { replace: false });
    if (typeof window !== 'undefined') {
      window.requestAnimationFrame(() => {
        window.scrollTo({ top: 0, behavior: activeTab === nextTab ? 'smooth' : 'auto' });
      });
    }
  }
  const [sessions, setSessions] = useState(cachedSessions.sessions || []);
  const [buyerGroups, setBuyerGroups] = useState(cachedBuyerGroups);
  const [saleOrders, setSaleOrders] = useState(cachedSaleOrders);
  const [inventory, setInventory] = useState(cachedInventory);
  const [customers, setCustomers] = useState(cachedCustomers);
  const [reportRows, setReportRows] = useState(cachedReportRows);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === 'undefined') return activeTab === 'inventory';
    const saved = window.localStorage.getItem('ynf_company_sidebar_collapsed');
    if (saved != null) return saved === 'true';
    return activeTab === 'inventory' || window.innerWidth < 1480;
  });
  const [loading, setLoading] = useState(
    !(
      (cachedSessions.sessions || []).length ||
      (cachedBuyerGroups.rows || []).length ||
      (cachedSaleOrders.rows || []).length ||
      (cachedInventory.rows || []).length ||
      (cachedCustomers.rows || []).length ||
      (cachedReportRows.rows || []).length
    )
  );
  const [sessionDetail, setSessionDetail] = useState(null);
  // Company view is POS/admin, not live ops. 30s for stream status is plenty
  // (it only feeds a small banner / KPI tile). Alert settings change rarely.
  const { data: streamStatus } = usePolling('/api/stream_status', 30000);
  const { data: alertsData } = usePolling('/api/alerts', 15000);
  const { data: alertSettings } = usePolling('/api/alerts/settings', 3600000);
  const alertCount = (alertsData?.alerts || []).filter((a) => a.level === 'error' || a.level === 'warning').length;
  const trackedAlerts = (alertsData?.alerts || []).filter((alert) => alert.type === 'tracked_buyer_activity');
  const trackedUsernames = alertSettings?.tracked_usernames || [];
  const visibleNav = useMemo(() => {
    const allowedBranches = roleRule.branches ? new Set(roleRule.branches) : null;
    return COMPANY_NAV
      .filter((item) => !['live-selling', 'settings'].includes(item.id))
      .filter((item) => !allowedBranches || allowedBranches.has(item.id))
      .map((item) => ({
        ...item,
        children: (item.children || []).filter((child) => !allowedTabs || allowedTabs.has(child.id)),
      }))
      .filter((item) => (item.children || []).length > 0);
  }, [roleRule, allowedTabs]);

  useEffect(() => {
    let cancelled = false;
    fetchApi('/api/auth/me')
      .then((data) => {
        if (cancelled) return;
        setAuthUser(data?.user || null);
      })
      .catch(() => {
        if (cancelled) return;
        setAuthUser(null);
      })
      .finally(() => {
        if (!cancelled) setAuthLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!authLoaded) return;
    if (!requestedTab || rawTab !== resolvedUrlTab) {
      writeTabToUrl(resolvedUrlTab, { replace: true });
    }
  }, [authLoaded, rawTab, requestedTab, resolvedUrlTab, setSearchParams]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.scrollTo({ top: 0, behavior: 'auto' });
  }, [activeTab]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem('ynf_company_sidebar_collapsed', String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const hasSaved = window.localStorage.getItem('ynf_company_sidebar_collapsed') != null;
    if (hasSaved) return;
    setSidebarCollapsed(activeTab === 'inventory' || window.innerWidth < 1480);
  }, [activeTab]);

  useEffect(() => {
    let cancelled = false;
    if (
      !sessions.length &&
      !(buyerGroups.rows || []).length &&
      !(saleOrders.rows || []).length &&
      !(inventory.rows || []).length &&
      !(customers.rows || []).length
    ) setLoading(true);
    Promise.all([
      fetchApi(COMPANY_SESSIONS_PATH).catch(() => ({ sessions: [] })),
      fetchApi(COMPANY_BUYER_GROUPS_PATH).catch(() => ({ rows: [] })),
      fetchApi(COMPANY_SALE_ORDERS_OVERVIEW_PATH).catch(() => ({ rows: [] })),
      fetchApi(COMPANY_INVENTORY_OVERVIEW_PATH).catch(() => ({ rows: [] })),
      fetchApi(COMPANY_CUSTOMERS_OVERVIEW_PATH).catch(() => ({ rows: [] })),
    ]).then(([sessionData, buyerGroupData, saleOrderData, inventoryData, customerData]) => {
      if (cancelled) return;
      setSessions(sessionData.sessions || []);
      setBuyerGroups(buyerGroupData || { rows: [] });
      setSaleOrders(saleOrderData || { rows: [] });
      setInventory(inventoryData || { rows: [] });
      setCustomers(customerData || { rows: [] });
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if ((reportRows.rows || []).length) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      fetchApi(COMPANY_REPORTS_OVERVIEW_PATH)
        .then((reportData) => {
          if (cancelled) return;
          setReportRows(reportData || { rows: [] });
        })
        .catch(() => {
          if (cancelled) return;
          setReportRows({ rows: [] });
        });
    }, 1500);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [reportRows.rows]);

  useEffect(() => {
    if (activeTab !== 'inventory') return;
    if (cachedInventoryAll?.rows?.length && (cachedInventoryCategories?.rows || cachedInventoryCategories || []).length) return;
    let cancelled = false;
    Promise.all([
      fetchApi(inventoryAllCacheKey).catch(() => null),
      fetchApi('/api/inventory/categories').catch(() => null),
    ]).then(([inventoryAll, categoryData]) => {
      if (cancelled) return;
      if (inventoryAll?.rows) {
        setCachedApi(inventoryAllCacheKey, inventoryAll);
      }
      if (categoryData?.rows) {
        setCachedApi('/api/inventory/categories', categoryData);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [activeTab, cachedInventoryAll, cachedInventoryCategories, inventoryAllCacheKey]);

  const activeMeta = TAB_META[activeTab] || TAB_META.overview;

  return (
    <div
      className={`company-shell company-shell-light is-tab-${activeTab}`}
      style={{
        display: 'flex',
        minWidth: 0,
        overflow: 'hidden',
        background: 'var(--bg-base)',
        height: 'calc(100dvh - 108px)',
        minHeight: 'calc(100dvh - 108px)',
        maxHeight: 'calc(100dvh - 108px)',
      }}
    >
      <aside
        className="company-sidebar"
        style={{
          width: sidebarCollapsed ? 78 : 260,
          minWidth: sidebarCollapsed ? 78 : 260,
          transition: 'width 180ms ease, min-width 180ms ease',
          overflow: 'hidden',
        }}
      >
        <div
          className="company-sidebar-brand"
          style={{
            padding: sidebarCollapsed ? '12px 10px' : undefined,
            justifyContent: sidebarCollapsed ? 'center' : undefined,
          }}
        >
          <img className="company-brand-mark" src={ynfLogo} alt="YNF Deals" />
          {!sidebarCollapsed ? (
            <div style={{ minWidth: 0 }}>
              <div className="company-sidebar-brand-title">YNF Deals</div>
              <div className="company-sidebar-brand-subtitle">Live Operations</div>
            </div>
          ) : null}
          <button
            type="button"
            onClick={() => setSidebarCollapsed((value) => !value)}
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            style={{
              marginLeft: sidebarCollapsed ? 0 : 'auto',
              width: 28,
              height: 28,
              borderRadius: 10,
              border: '1px solid var(--border-default)',
              background: 'var(--bg-panel)',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              display: 'grid',
              placeItems: 'center',
              flexShrink: 0,
            }}
          >
            {sidebarCollapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
          </button>
        </div>

        {!sidebarCollapsed ? <div className="company-sidebar-section-label">Operate</div> : null}
        <nav className="company-sidebar-nav">
          {visibleNav.map((item) => (
            <SidebarNode
              key={item.id}
              item={item}
              activeTab={activeTab}
              setActiveTab={setActiveTab}
              collapsed={sidebarCollapsed}
            />
          ))}
        </nav>

        {!sidebarCollapsed ? (
          <div className="company-sidebar-footer">
            <div className="company-sidebar-footer-card">
              <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#94a3b8' }}>Operations Risk</div>
              <div style={{ marginTop: 8, fontSize: 24, fontWeight: 900, letterSpacing: '-0.03em', color: '#0f172a' }}>{alertCount}</div>
              <div style={{ marginTop: 4, fontSize: 12, color: '#64748b' }}>
                {viewerRole === 'admin'
                  ? 'Warnings, diagnostics, and tracked activity waiting for review.'
                  : 'Simplified workspace for daily sales and inventory operations.'}
              </div>
            </div>
          </div>
        ) : null}
      </aside>

      <div className="company-main-shell">
        {!['inventory', 'orders', 'tiktok-shop-sales', 'tiktok-live-sales', 'tiktok-returns', 'tiktok-go-live', 'tiktok'].includes(activeTab) ? (
          <div className="company-content-topbar">
            <div>
              <div className="company-content-eyebrow">YNF Deals Control Tower</div>
              <h1 className="company-content-title">{activeMeta.title}</h1>
              <p className="company-content-subtitle">{activeMeta.description}</p>
            </div>
            <div className={`company-content-status ${streamStatus?.live ? 'is-live' : ''}`}>
              <span />
              {streamStatus?.live ? 'Live stream active' : 'Ready'}
            </div>
          </div>
        ) : null}

        <div className="company-content-surface">
          <div style={{ flex: '1 1 auto', minWidth: 0, minHeight: 0, overflow: 'visible' }}>
            {loading && activeTab === 'overview' ? (
              <Panel title="Loading">
                <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Loading company data...</div>
              </Panel>
            ) : null}
            {!loading && activeTab === 'overview' ? (
              <ModernOverview
                sessions={sessions}
                inventory={inventory}
                buyerGroups={buyerGroups}
                saleOrders={saleOrders}
                customers={customers}
                reportRows={reportRows}
                streamStatus={streamStatus}
                trackedUsernames={trackedUsernames}
                trackedAlerts={trackedAlerts}
                onTabChange={setActiveTab}
              />
            ) : null}
            {!loading && activeTab === 'finances' ? <FinanceHub sessions={sessions} /> : null}
            {!loading && activeTab === 'our-company' ? <OurCompanyHub sessions={sessions} inventory={inventory} saleOrders={saleOrders} onTabChange={setActiveTab} /> : null}
            {!loading && activeTab === 'sessions' ? <SessionsTab sessions={sessions} onSessionClick={setSessionDetail} /> : null}
            {activeTab === 'mega-dashboard' ? (
              <Suspense fallback={<CompanyLazyFallback label="Loading dashboard..." />}>
                <MegaDashboard onTabChange={setActiveTab} />
              </Suspense>
            ) : null}
            {['uploads', 'uploads-tiktok', 'uploads-affiliate'].includes(activeTab) ? <UploadsWorkspace activeSection={activeTab} /> : null}
            {activeTab === 'auction-results-hub' ? <AuctionResultsHub onTabChange={setActiveTab} /> : null}
            {['orders', 'orders-whatnot', 'auction-results', 'sessions', 'tiktok', 'tiktok-go-live', 'tiktok-live-sales', 'tiktok-shop-sales', 'tiktok-returns', 'orders-affiliate', 'in-house-sales', 'uploads-tiktok'].includes(activeTab) ? (
              <SalesWorkspace
                activeSection={activeTab}
                sessions={sessions}
                saleOrders={saleOrders}
                inventory={inventory}
                buyerGroups={buyerGroups}
                customers={customers}
                reportRows={reportRows}
                onSessionClick={setSessionDetail}
              />
            ) : null}
            {ACCOUNT_MANAGEMENT_TABS.has(activeTab) ? <AccountsHub activeSection={activeTab} onTabChange={setActiveTab} /> : null}
            {activeTab === 'employee-management' ? (
              <Suspense fallback={<CompanyLazyFallback label="Loading employee tools..." />}>
                <EmployeeManagement />
              </Suspense>
            ) : null}
            {activeTab === 'in-house-approvals' ? (
              <Suspense fallback={<CompanyLazyFallback label="Loading approvals..." />}>
                <InHouseApprovals />
              </Suspense>
            ) : null}
            {activeTab === 'inventory' ? (
              <div className="company-inventory-frame">
                <Suspense fallback={<CompanyLazyFallback label="Loading inventory..." />}>
                  <CompanyInventory initialData={cachedInventoryAll || inventory} initialCategories={cachedInventoryCategories} />
                </Suspense>
              </div>
            ) : null}
            {activeTab === 'purchases' ? (
              <Suspense fallback={<CompanyLazyFallback label="Loading purchases..." />}>
                <Purchases />
              </Suspense>
            ) : null}
            {activeTab === 'packing-scanner' ? (
              <Suspense fallback={<CompanyLazyFallback label="Loading packing scanner..." />}>
                <PackingScanner />
              </Suspense>
            ) : null}
            {activeTab === 'packing-alerts' ? (
              <Suspense fallback={<CompanyLazyFallback label="Loading packing alerts..." />}>
                <PackingAlerts />
              </Suspense>
            ) : null}
            {activeTab === 'pricelists' ? <PricelistsWorkspace onTabChange={setActiveTab} /> : null}
            {activeTab === 'prep' ? (
              <Suspense fallback={<CompanyLazyFallback label="Loading prep tools..." />}>
                <Prep />
              </Suspense>
            ) : null}
            {activeTab === 'customers' ? (
              <Suspense fallback={<CompanyLazyFallback label="Loading customers..." />}>
                <Customers />
              </Suspense>
            ) : null}
            {activeTab === 'picklist' ? (
              <Suspense fallback={<CompanyLazyFallback label="Loading pick list..." />}>
                <PickList sessions={sessions} />
              </Suspense>
            ) : null}
            {activeTab === 'intelligence' ? (
              <Suspense fallback={<CompanyLazyFallback label="Loading intelligence..." />}>
                <CompanyIntelligence />
              </Suspense>
            ) : null}
            {activeTab === 'graphs' ? (
              <Suspense fallback={<CompanyLazyFallback label="Loading charts..." />}>
                <GraphsDashboard />
              </Suspense>
            ) : null}
            {activeTab === 'diagnostics' ? (
              <Suspense fallback={<CompanyLazyFallback label="Loading diagnostics..." />}>
                <Diagnostics />
              </Suspense>
            ) : null}
            {activeTab === 'settings' ? (
              <Suspense fallback={<CompanyLazyFallback label="Loading settings..." />}>
                <Settings />
              </Suspense>
            ) : null}
          </div>
        </div>
      </div>

      {sessionDetail && (
        <Suspense fallback={null}>
          <SessionDetail sessionId={sessionDetail} onClose={() => setSessionDetail(null)} />
        </Suspense>
      )}
    </div>
  );
}
