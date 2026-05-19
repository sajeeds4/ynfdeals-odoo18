const { useEffect, useMemo, useState } = React;

const API_BASE = "http://localhost:8088";

function formatTime(ts) {
  if (!ts) return "—";
  return ts.replace("T", " ").replace("+00:00", " UTC");
}

function App() {
  const [status, setStatus] = useState("Disconnected");
  const [tab, setTab] = useState("live");
  const [lastId, setLastId] = useState(0);
  const [liveStartId, setLiveStartId] = useState(0);
  const [chat, setChat] = useState([]);
  const [wins, setWins] = useState([]);
  const [buyers, setBuyers] = useState([]);
  const [active, setActive] = useState({
    product: "—",
    lot: "—",
    status: "waiting",
    price: "$—",
    winner: "—",
    time: "—",
  });
  const [metrics, setMetrics] = useState({
    sold: 0,
    revenue: 0,
    avg: 0,
    completed: 0,
    activeLot: "—",
    viewers: "—",
    topChatters: [],
  });

  const chatCounts = useMemo(() => new Map(), []);
  const buyerStats = useMemo(() => new Map(), []);

  const updateMetrics = () => {
    const top = Array.from(chatCounts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([name, count]) => `${name} (${count})`);
    setMetrics((m) => ({ ...m, topChatters: top }));
  };

  const renderBuyers = () => {
    const rows = Array.from(buyerStats.entries())
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, 50)
      .map(([buyer, stats]) => {
        const topProducts = Array.from(stats.products.entries())
          .sort((a, b) => b[1] - a[1])
          .slice(0, 3)
          .map(([name, count]) => `${name} (${count})`)
          .join(", ");
        const avg = stats.pricedCount ? stats.total / stats.pricedCount : 0;
        return {
          buyer,
          line: `Buys: ${stats.count} | Spent: $${stats.total.toFixed(2)} | Avg: $${avg.toFixed(2)} | Top: ${topProducts || "—"}`,
        };
      });
    setBuyers(rows);
  };

  const resetLive = async () => {
    const res = await fetch(`${API_BASE}/latest_id`);
    const data = await res.json();
    setLastId(data.latest_id || 0);
    setLiveStartId(data.latest_id || 0);
    setChat([]);
    setWins([]);
  };

  const loadRecent = async () => {
    const res = await fetch(`${API_BASE}/recent?limit=200`);
    const data = await res.json();
    data.events.forEach((e) => handleEvent(e, false));
  };

  const handleEvent = (e, isLive) => {
    if (liveStartId && e.id <= liveStartId && isLive) return;

    let parsed = {};
    try { parsed = JSON.parse(e.payload || "{}"); } catch {}

    if (e.event_type === "chat_message") {
      setChat((prev) => [{ time: formatTime(e.created_at), text: `${parsed.username || ""}: ${parsed.message || ""}` }, ...prev].slice(0, 500));
      const name = parsed.username || "unknown";
      chatCounts.set(name, (chatCounts.get(name) || 0) + 1);
      updateMetrics();
    }

    if (e.event_type === "lot_update") {
      setActive((prev) => ({
        ...prev,
        lot: parsed.lot_number || "—",
        status: "live",
        time: formatTime(e.created_at),
      }));
      setMetrics((m) => ({ ...m, activeLot: parsed.lot_number || "—" }));
    }

    if (e.event_type === "bid_update") {
      setActive((prev) => ({ ...prev, price: parsed.price || prev.price }));
    }

    if (e.event_type === "auction_winner") {
      const priceValue = parsed.price_value ? Number(parsed.price_value) : 0;
      setActive((prev) => ({
        ...prev,
        status: "sold",
        winner: parsed.winner || "—",
        price: parsed.price || prev.price,
        time: formatTime(e.created_at),
      }));
      setWins((prev) => [{
        time: formatTime(e.created_at),
        text: `${parsed.winner || ""} | ${parsed.price || ""} | Lot ${parsed.lot_number || ""}`,
      }, ...prev].slice(0, 500));

      setMetrics((m) => {
        const sold = m.sold + 1;
        const completed = m.completed + 1;
        const revenue = m.revenue + (priceValue || 0);
        const avg = completed ? revenue / completed : 0;
        return { ...m, sold, completed, revenue, avg };
      });

      const buyer = parsed.winner || "unknown";
      const stats = buyerStats.get(buyer) || { count: 0, total: 0, pricedCount: 0, products: new Map() };
      stats.count += 1;
      if (priceValue) {
        stats.total += priceValue;
        stats.pricedCount += 1;
      }
      buyerStats.set(buyer, stats);
      renderBuyers();
    }

    if (e.event_type === "live_viewers") {
      setMetrics((m) => ({ ...m, viewers: parsed.count || "—" }));
    }
  };

  const poll = async () => {
    try {
      const res = await fetch(`${API_BASE}/events?since=${lastId}`);
      const data = await res.json();
      setStatus("Connected");
      data.events.forEach((e) => {
        setLastId((prev) => Math.max(prev, e.id));
        handleEvent(e, true);
      });
    } catch {
      setStatus("Disconnected");
    }
  };

  useEffect(() => {
    (async () => {
      const res = await fetch(`${API_BASE}/latest_id`);
      const data = await res.json();
      setLastId(data.latest_id || 0);
      setLiveStartId(data.latest_id || 0);
      poll();
      const id = setInterval(poll, 1000);
      return () => clearInterval(id);
    })();
  }, []);

  return (
    <div className="app">
      <div className="header">
        <div className="brand">
          <div className="logo">WL</div>
          <div>
            <h1>Whatnot Live Control</h1>
            <div className="controls">
              <span>Realtime dashboard</span>
            </div>
          </div>
        </div>
        <div className="controls">
          <button onClick={resetLive}>Reset to Now</button>
          <button onClick={loadRecent}>Load Recent</button>
          <span className="status-pill">{status}</span>
        </div>
      </div>

      <div className="content">
        <div className="grid">
          <div className="panel">
            <h2>Live Control</h2>
            <div className="live-card">
              <div className="live-title">{active.product}</div>
              <div className="live-meta">
                <span>Lot {active.lot}</span>
                <span className={`badge ${active.status === "sold" ? "sold" : "live"}`}>
                  {active.status === "sold" ? "sold" : "live"}
                </span>
                <span>{active.time}</span>
              </div>
              <div className="live-price">{active.price}</div>
              <div className="live-meta">Winner: {active.winner}</div>
            </div>
          </div>

          <div className="panel">
            <h2>Live Metrics</h2>
            <div className="metrics">
              <div className="metric"><div className="label">Sold</div><div className="value">{metrics.sold}</div></div>
              <div className="metric"><div className="label">Revenue</div><div className="value">${metrics.revenue.toFixed(2)}</div></div>
              <div className="metric"><div className="label">Avg Price</div><div className="value">${metrics.avg.toFixed(2)}</div></div>
              <div className="metric"><div className="label">Completed</div><div className="value">{metrics.completed}</div></div>
              <div className="metric"><div className="label">Active Lot</div><div className="value">{metrics.activeLot}</div></div>
              <div className="metric"><div className="label">Viewers</div><div className="value">{metrics.viewers}</div></div>
            </div>
            <div style={{ marginTop: "12px", color: "var(--muted)", fontSize: "12px" }}>
              Top chatters: {metrics.topChatters.length ? metrics.topChatters.join(", ") : "—"}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="tabs">
            <button className={tab === "live" ? "active" : ""} onClick={() => setTab("live")}>Live Feed</button>
            <button className={tab === "wins" ? "active" : ""} onClick={() => setTab("wins")}>Auction Wins</button>
            <button className={tab === "buyers" ? "active" : ""} onClick={() => setTab("buyers")}>Buyers</button>
          </div>

          {tab === "live" && (
            <div className="subgrid">
              <div className="list">
                {chat.map((m, idx) => (
                  <div className="row" key={idx}>
                    <div className="time">{m.time}</div>
                    <div className="payload">{m.text}</div>
                  </div>
                ))}
              </div>
              <div className="list">
                {wins.map((m, idx) => (
                  <div className="row" key={idx}>
                    <div className="time">{m.time}</div>
                    <div className="payload">{m.text}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {tab === "wins" && (
            <div className="list">
              {wins.map((m, idx) => (
                <div className="row" key={idx}>
                  <div className="time">{m.time}</div>
                  <div className="payload">{m.text}</div>
                </div>
              ))}
            </div>
          )}

          {tab === "buyers" && (
            <div className="list">
              {buyers.map((b, idx) => (
                <div className="row" key={idx}>
                  <div className="time">{b.buyer}</div>
                  <div className="payload">{b.line}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
