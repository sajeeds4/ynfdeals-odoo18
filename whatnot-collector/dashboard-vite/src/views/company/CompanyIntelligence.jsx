import { usePolling } from '../../hooks/useApi';
import { KpiCard, PrimaryBtn, TableShell, Thead, EmptyRow, fmtDt } from './utils';

const fmt = (n) => (n == null ? '—' : `$${Number(n).toFixed(2)}`);
const fmtHour = (hour) => new Date(2000, 0, 1, Number(hour || 0)).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
const profitColor = (n) => (Number(n || 0) >= 0 ? 'var(--accent-emerald)' : 'var(--accent-coral)');

function renderLiveSuggestion(item) {
  if (item && typeof item === 'object') {
    const productName = item.product_name || item.name;
    return (
      <>
        {item.message || item.text || ''}
        {productName ? (
          <>
            {' '}
            <strong>{productName}</strong>
            {item.retail_price != null ? ` · Retail ${fmt(item.retail_price)}` : ''}
            {item.our_cost != null ? ` · Our cost ${fmt(item.our_cost)}` : ''}
          </>
        ) : null}
      </>
    );
  }
  return item;
}

function Section({ title, sub, children }) {
  return (
    <section className="company-panel">
      <div className="company-panel-head">
        <div>
          <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--text-primary)' }}>{title}</div>
          {sub ? <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>{sub}</div> : null}
        </div>
      </div>
      <div style={{ padding: '16px 18px' }}>
        {children}
      </div>
    </section>
  );
}

export default function CompanyIntelligence() {
  const {
    data,
    loading,
    error,
    refresh: load,
  } = usePolling('/api/company/intelligence', 10000);

  const summary = data?.summary || {};
  const rec = data?.recommendations || {};
  const liveMode = data?.live_mode || { running: false, suggestions: [] };
  const advancedModels = data?.advanced_models || {};
  const nextBestProducts = advancedModels.next_best_products || [];
  const buyerIntentScores = advancedModels.buyer_intent_scores || [];
  const lotHealth = advancedModels.lot_health || [];
  const priceExpectations = advancedModels.price_expectations || [];
  const bestHourLabel = rec.best_start_time_hour != null ? fmtHour(rec.best_start_time_hour) : '—';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 900 }}>Livestream Sales Intelligence</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
            Time profitability, day performance, behavior, chat conversion, product intelligence, and live recommendations.
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, fontSize: 11, color: 'var(--text-secondary)' }}>
            <span style={{
              width: 8,
              height: 8,
              borderRadius: 999,
              background: error ? 'var(--accent-coral)' : 'var(--accent-emerald)',
              display: 'inline-block',
            }} />
            {error ? `Real-time refresh error: ${error}` : 'Auto-refreshing every 10s'}
          </div>
        </div>
        <PrimaryBtn onClick={load}>{loading ? 'Refreshing…' : 'Refresh Intelligence'}</PrimaryBtn>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
        <KpiCard label="Best Day" value={rec.best_day_to_go_live || '—'} icon="📅" />
        <KpiCard label="Best Start" value={bestHourLabel} icon="⏰" />
        <KpiCard label="Peak Profit" value={summary.peak_profit_window || '—'} icon="💰" color="var(--accent-amber)" />
        <KpiCard label="Avg Time To Buy" value={summary.avg_minutes_to_buy != null ? `${summary.avg_minutes_to_buy}m` : '—'} icon="🕒" />
        <KpiCard label="Repeat Buyers" value={summary.repeat_buyer_count ?? 0} icon="🔁" color="var(--accent-emerald)" />
        <KpiCard label="Unpaid Winners" value={summary.unpaid_order_count ?? 0} icon="⚠️" color={(summary.unpaid_order_count || 0) > 0 ? 'var(--accent-coral)' : 'var(--text-primary)'} />
      </div>

      <Section title="Recommended Strategy" sub="Best day, best start time, expected revenue range, and session flow.">
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 16 }}>
          <div style={{ display: 'grid', gap: 10 }}>
            <div style={{ padding: '12px 14px', borderRadius: 14, background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.18)' }}>
              Best day to go live: <strong>{rec.best_day_to_go_live || '—'}</strong>
            </div>
            <div style={{ padding: '12px 14px', borderRadius: 14, background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.18)' }}>
              Best start time: <strong>{bestHourLabel}</strong>
            </div>
            <div style={{ padding: '12px 14px', borderRadius: 14, background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.18)' }}>
              Expected revenue range: <strong>{fmt(rec.expected_revenue_low)} - {fmt(rec.expected_revenue_high)}</strong>
            </div>
          </div>
          <div style={{ display: 'grid', gap: 10 }}>
            {(rec.best_product_sequence_strategy || []).map((item, index) => (
              <div key={index} style={{ padding: '12px 14px', borderRadius: 14, background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', fontSize: 13 }}>
                {item}
              </div>
            ))}
            {(rec.dropoff_windows || []).length ? (
              <div style={{ padding: '12px 14px', borderRadius: 14, background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.18)', fontSize: 13 }}>
                Drop-off windows: <strong>{rec.dropoff_windows.join(', ')}</strong>
              </div>
            ) : null}
          </div>
        </div>
      </Section>

      <Section title="Real-Time Mode" sub="Compares current live performance to historical behavior and suggests interventions.">
        <div style={{ display: 'grid', gap: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: liveMode.running ? 'var(--accent-emerald)' : 'var(--text-secondary)' }}>
            {liveMode.running ? 'Live stream detected' : 'No live stream currently running'}
          </div>
          {(liveMode.suggestions || []).length ? (
            liveMode.suggestions.map((item, index) => (
              <div key={index} style={{ padding: '12px 14px', borderRadius: 14, background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.18)', fontSize: 13 }}>
                {renderLiveSuggestion(item)}
              </div>
            ))
          ) : (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Suggestions will appear here during a live stream when performance deviates from historical norms.</div>
          )}
        </div>
      </Section>

      <Section title="Live Decision Models" sub="Next product ranking, buyer intent scoring, lot-health risk, and expected price ranges from your own session history.">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div style={{ display: 'grid', gap: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 800, color: 'var(--accent-emerald)', textTransform: 'uppercase' }}>Next Best Products</div>
            {!nextBestProducts.length ? (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>No next-product model output yet.</div>
            ) : nextBestProducts.slice(0, 6).map((row, index) => (
              <div key={`${row.product_name}-${index}`} style={{ padding: '12px 14px', borderRadius: 14, background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.18)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                  <strong>{row.product_name}</strong>
                  <span style={{ color: 'var(--accent-emerald)', fontWeight: 800 }}>{row.score}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>{(row.why || []).join(' · ')}</div>
              </div>
            ))}
          </div>

          <div style={{ display: 'grid', gap: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 800, color: 'var(--accent-blue)', textTransform: 'uppercase' }}>Buyer Intent Scores</div>
            {!buyerIntentScores.length ? (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>No buyer-intent scoring yet.</div>
            ) : buyerIntentScores.slice(0, 8).map((row) => (
              <div key={row.username} style={{ padding: '12px 14px', borderRadius: 14, background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.18)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                  <strong>@{row.username}</strong>
                  <span style={{ color: row.intent_score >= 70 ? 'var(--accent-emerald)' : 'var(--accent-amber)', fontWeight: 800 }}>{row.intent_score}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                  {row.recent_messages} chats · {row.bid_count} bids · hist {fmt(row.historical_revenue)}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 800, color: 'var(--accent-coral)', textTransform: 'uppercase', marginBottom: 8 }}>Lot Health</div>
            {!lotHealth.length ? (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>No lot-health tracking yet.</div>
            ) : (
              <div style={{ display: 'grid', gap: 8 }}>
                {lotHealth.map((row, index) => (
                  <div key={`${row.lot_number}-${index}`} style={{ padding: '12px 14px', borderRadius: 14, background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                      <strong>Lot {row.lot_number} · {row.product_name}</strong>
                      <span style={{ color: row.status === 'stalling' ? 'var(--accent-coral)' : row.status === 'hot' ? 'var(--accent-emerald)' : 'var(--accent-blue)', fontWeight: 800 }}>
                        {row.status} · {row.stall_risk}%
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                      Conversion score {row.conversion_score} · Final sale {fmt(row.final_sale)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <div style={{ fontSize: 12, fontWeight: 800, color: 'var(--accent-amber)', textTransform: 'uppercase', marginBottom: 8 }}>Price Expectations</div>
            <TableShell footer={`${priceExpectations.length} product model row(s)`}>
              <Thead cols={[
                { label: 'Product' },
                { label: 'Expected', align: 'right' },
                { label: 'Median', align: 'right' },
              ]} />
              <tbody>
                {!priceExpectations.length ? <EmptyRow cols={3} msg="No price expectation model rows yet." /> : priceExpectations.slice(0, 10).map((row, index) => (
                  <tr key={`${row.product_name}-${index}`} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '8px 14px', fontWeight: 700 }}>{row.product_name}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-blue)', fontWeight: 700 }}>
                      {fmt(row.expected_price_range?.low)} - {fmt(row.expected_price_range?.high)}
                    </td>
                    <td style={{ padding: '8px 14px', textAlign: 'right' }}>{fmt(row.expected_price_range?.mid)}</td>
                  </tr>
                ))}
              </tbody>
            </TableShell>
          </div>
        </div>
      </Section>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Section title="Hourly Profitability" sub="Revenue, profit, and conversion performance by hour.">
          <TableShell footer={`${(data?.hourly || []).length} hourly bucket(s)`}>
            <Thead cols={[
              { label: 'Hour' },
              { label: 'Revenue', align: 'right' },
              { label: 'Profit', align: 'right' },
              { label: 'Avg Bid', align: 'right' },
              { label: 'Conv %', align: 'right' },
            ]} />
            <tbody>
              {!(data?.hourly || []).length ? <EmptyRow cols={5} msg="No hourly data found." /> : (data.hourly || []).filter((row) => row.revenue > 0 || row.chat_count > 0 || row.bid_count > 0).map((row) => (
                <tr key={row.hour} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '8px 14px' }}>{String(row.hour).padStart(2, '0')}:00</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(row.revenue)}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', color: profitColor(row.profit), fontWeight: 700 }}>{fmt(row.profit)}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right' }}>{fmt(row.avg_bid)}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.conversion_rate}%</td>
                </tr>
              ))}
            </tbody>
          </TableShell>
        </Section>

        <Section title="Day-Based Performance" sub="Which days bring the best profit, engagement, and conversion.">
          <TableShell footer={`${(data?.by_day || []).length} day(s)`}>
            <Thead cols={[
              { label: 'Day' },
              { label: 'Avg Rev', align: 'right' },
              { label: 'Avg Profit', align: 'right' },
              { label: 'Engagement', align: 'right' },
              { label: 'Conv %', align: 'right' },
            ]} />
            <tbody>
              {!(data?.by_day || []).length ? <EmptyRow cols={5} msg="No day data found." /> : (data.by_day || []).map((row) => (
                <tr key={row.day} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '8px 14px' }}>{row.day}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(row.avg_revenue_per_session)}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', color: profitColor(row.avg_profit_per_session), fontWeight: 700 }}>{fmt(row.avg_profit_per_session)}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.engagement}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.conversion_rate}%</td>
                </tr>
              ))}
            </tbody>
          </TableShell>
        </Section>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Section title="Buyer Behavior" sub="High-value repeat buyers and buyers who win without much visible chat activity.">
          <div style={{ display: 'grid', gap: 8 }}>
            {(data?.top_buyers || []).slice(0, 10).map((buyer) => (
              <div key={buyer.username} style={{ padding: '10px 12px', borderRadius: 12, background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                  <strong>@{buyer.username}</strong>
                  <span style={{ color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(buyer.revenue)}</span>
                </div>
                <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)' }}>
                  {buyer.orders} wins · {buyer.session_count} session(s) · Profit {fmt(buyer.profit)}
                </div>
              </div>
            ))}
            {(data?.silent_buyers || []).length ? (
              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                Silent / low-chat buyers: {(data.silent_buyers || []).join(', ')}
              </div>
            ) : null}
          </div>
        </Section>

        <Section title="Chat to Purchase Signals" sub="Keywords and language patterns that show up before conversions.">
          <TableShell footer={`${(data?.chat_keywords || []).length} keyword(s)`}>
            <Thead cols={[
              { label: 'Keyword' },
              { label: 'Mentions', align: 'right' },
              { label: 'Conversions', align: 'right' },
              { label: 'Score', align: 'right' },
            ]} />
            <tbody>
              {!(data?.chat_keywords || []).length ? <EmptyRow cols={4} msg="No chat-conversion keywords found yet." /> : (data.chat_keywords || []).slice(0, 12).map((row) => (
                <tr key={row.keyword} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '8px 14px', fontWeight: 700 }}>{row.keyword}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.mentions}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.conversions}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-blue)' }}>{row.conversion_score}</td>
                </tr>
              ))}
            </tbody>
          </TableShell>
        </Section>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <Section title="Top Bidders" sub="Available when bidder usernames are exposed by the auction UI and captured by the collector.">
          <TableShell footer={`${(data?.top_bidders || []).length} bidder(s)`}>
            <Thead cols={[
              { label: 'Bidder' },
              { label: 'Bids', align: 'right' },
              { label: 'Lots', align: 'right' },
              { label: 'Max Bid', align: 'right' },
            ]} />
            <tbody>
              {!(data?.top_bidders || []).length ? <EmptyRow cols={4} msg="No named bidder events captured yet." /> : (data.top_bidders || []).map((row) => (
                <tr key={row.username} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '8px 14px', fontWeight: 700 }}>@{row.username}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.bid_count}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.lot_count}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(row.max_bid)}</td>
                </tr>
              ))}
            </tbody>
          </TableShell>
        </Section>

        <Section title="Repeat Buyers" sub="Winners who keep buying across multiple streams.">
          <TableShell footer={`${(data?.repeat_buyers || []).length} repeat buyer(s)`}>
            <Thead cols={[
              { label: 'Buyer' },
              { label: 'Sessions', align: 'right' },
              { label: 'Wins', align: 'right' },
              { label: 'Revenue', align: 'right' },
            ]} />
            <tbody>
              {!(data?.repeat_buyers || []).length ? <EmptyRow cols={4} msg="No repeat buyers detected yet." /> : (data.repeat_buyers || []).map((row) => (
                <tr key={row.username} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '8px 14px', fontWeight: 700 }}>@{row.username}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.session_count}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.orders}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(row.revenue)}</td>
                </tr>
              ))}
            </tbody>
          </TableShell>
        </Section>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 16 }}>
        <Section title="Product Intelligence" sub="Profit, competition, and best time/day for products.">
          <TableShell footer={`${(data?.products || []).length} product(s)`}>
            <Thead cols={[
              { label: 'Product' },
              { label: 'Revenue', align: 'right' },
              { label: 'Profit', align: 'right' },
              { label: 'Margin %', align: 'right' },
              { label: 'Competition', align: 'right' },
              { label: 'Best Time' },
            ]} />
            <tbody>
              {!(data?.products || []).length ? <EmptyRow cols={6} msg="No product intelligence found." /> : (data.products || []).slice(0, 15).map((row, index) => (
                <tr key={`${row.product_name}-${index}`} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '8px 14px', fontWeight: 700 }}>{row.product_name}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(row.revenue)}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', color: profitColor(row.profit), fontWeight: 700 }}>{fmt(row.profit)}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.margin_pct}%</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.competition_score}</td>
                  <td style={{ padding: '8px 14px' }}>{row.best_day || '—'}{row.best_hour != null ? ` · ${String(row.best_hour).padStart(2, '0')}:00` : ''}</td>
                </tr>
              ))}
            </tbody>
          </TableShell>
        </Section>

        <Section title="Viewer and Product Timeline" sub="Uses currently captured viewer snapshots and product-show history.">
          <div style={{ display: 'grid', gap: 12 }}>
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Viewer Count Over Time</div>
              <div style={{ maxHeight: 180, overflow: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <tbody>
                    {!(data?.viewer_history || []).length ? (
                      <tr><td style={{ color: 'var(--text-secondary)' }}>No viewer history captured yet.</td></tr>
                    ) : (data.viewer_history || []).slice(-12).map((row, index) => (
                      <tr key={index} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '6px 0', color: 'var(--text-secondary)' }}>{fmtDt(row.time)}</td>
                        <td style={{ padding: '6px 0', textAlign: 'right', fontWeight: 700 }}>{row.viewer_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Product Show → Chat → Sale</div>
              <div style={{ maxHeight: 220, overflow: 'auto' }}>
                {(data?.product_timeline || []).slice(-10).reverse().map((row, index) => (
                  <div key={index} style={{ padding: '10px 12px', borderRadius: 12, background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', marginBottom: 8 }}>
                    <div style={{ fontWeight: 700 }}>{row.product_name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                      Lot {row.lot_number} · {fmtDt(row.shown_at)}
                    </div>
                    <div style={{ fontSize: 12, marginTop: 4 }}>
                      {row.chat_count_10m} chats from {row.unique_chatters_10m} users · {row.bid_count_10m} bids from {row.unique_bidders_10m} bidders · Final sale {fmt(row.final_sale)}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                      Viewer flow {row.viewer_joins_10m >= 0 ? '+' : ''}{row.viewer_joins_10m} / -{row.viewer_leaves_10m} ({row.viewer_net_10m >= 0 ? '+' : ''}{row.viewer_net_10m} net) · Conversion score {row.conversion_score}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                      {row.seconds_to_sale != null ? `Time to sale: ${row.seconds_to_sale}s` : 'No final sale captured yet'}{row.winner ? ` · Winner @${row.winner}` : ''}{row.named_bid_count_10m ? ` · ${row.named_bid_count_10m} named bid(s)` : ''}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Section>
      </div>

      <Section title="Data Coverage" sub="What is fully tracked now vs what still needs collector upgrades.">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 800, color: 'var(--accent-emerald)', textTransform: 'uppercase', marginBottom: 8 }}>Tracked Now</div>
            <div style={{ display: 'grid', gap: 6, fontSize: 13 }}>
              <div>Hourly revenue and profit windows</div>
              <div>Day-of-week profitability and conversion</div>
              <div>Chat activity and keyword conversion signals</div>
              <div>Product shown timestamp history</div>
              <div>Live viewer count snapshots over time</div>
              <div>Repeat buyer behavior across streams</div>
              <div>Unpaid order / unpaid winner signals</div>
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 800, color: 'var(--accent-amber)', textTransform: 'uppercase', marginBottom: 8 }}>Needs New Collector Signals</div>
            <div style={{ display: 'grid', gap: 6, fontSize: 13 }}>
              {(data?.data_limits || []).map((item, index) => (
                <div key={index}>{item}</div>
              ))}
              <div>Exact viewer join timestamps</div>
              <div>Exact viewer leave timestamps</div>
              <div>Bidder username on every bid event</div>
            </div>
          </div>
        </div>
      </Section>
    </div>
  );
}
