import type{ MetricState, Pod } from '../services/MockDataLayer';

interface MetricsPanelProps {
  metrics: MetricState;
  pods: Pod[];
}

export function MetricsPanel({ metrics, pods }: MetricsPanelProps) {
  const formatCost = (cost: number) => {
    if (cost < 0.01) return `$${cost.toFixed(4)}`;
    return `$${cost.toFixed(2)}`;
  };

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const workers = pods.filter(p => p.role === 'worker');

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>

      {/* Top Half: Quantitative */}
      <div style={{ padding: '1.25rem', borderBottom: '1px solid var(--glass-border)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>

        <MetricCard label="Tokens Used" value={metrics.tokensUsed.toLocaleString()} />
        <MetricCard label="Est. Cost" value={formatCost(metrics.estimatedCost)} />
        <MetricCard label="Tavily Calls" value={metrics.tavilyCalls.toString()} />
        <MetricCard label="Active Workers" value={`${metrics.activeWorkers} / ${workers.length}`} />
        <MetricCard label="Rounds" value={`${metrics.roundsCompleted} / ${metrics.maxRounds}`} />
        <MetricCard label="Elapsed Time" value={formatTime(metrics.timeElapsed)} />

      </div>

      {/* Bottom Half: Qualitative */}
      <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>

        <div>
          <h4 style={{ marginBottom: '8px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>Stance Roster</h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            {workers.map(w => (
              <span key={w.id} style={{
                background: 'rgba(16, 185, 129, 0.1)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                padding: '4px 8px',
                borderRadius: '12px',
                fontSize: '0.75rem',
                color: 'var(--text-main)',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}>
                <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--color-worker)' }} />
                {w.stance || 'Unknown'}
              </span>
            ))}
          </div>
        </div>

        <div>
          <h4 style={{ marginBottom: '8px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>Divergence Heatmap</h4>
          <div style={{ display: 'flex', gap: '4px', height: '24px' }}>
            {workers.map(w => {
              const divVal = typeof w.divergence === 'number' ? w.divergence : 0;
              // Heatmap color from safe to danger based on divergence
              const color = `rgb(${Math.floor(255 * divVal)}, ${Math.floor(255 * (1 - divVal))}, 100)`;
              return (
                <div key={w.id} style={{
                  flex: 1,
                  background: color,
                  borderRadius: '4px',
                  opacity: 0.8
                }} title={`Divergence: ${divVal.toFixed(2)}`} />
              );
            })}
          </div>
        </div>

        <div>
          <h4 style={{ marginBottom: '8px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>Consensus Confidence</h4>
          <div style={{ height: '60px', borderBottom: '1px solid var(--glass-border)', borderLeft: '1px solid var(--glass-border)', position: 'relative' }}>
            <svg width="100%" height="100%" preserveAspectRatio="none">
              <polyline
                points={metrics.confidence.map((val, i) => `${(i / Math.max(1, metrics.confidence.length - 1)) * 100},${100 - val * 100}`).join(' ')}
                fill="none"
                stroke="var(--color-judge)"
                strokeWidth="3"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
          </div>
        </div>

        {metrics.finalSentiment && (
          <div className="animate-slide-up" style={{
            background: 'var(--bg-card-hover)',
            padding: '1rem',
            borderRadius: '8px',
            border: '1px solid var(--color-judge)',
            boxShadow: '0 4px 12px rgba(139, 92, 246, 0.15)'
          }}>
            <h4 style={{ marginBottom: '12px', fontSize: '0.85rem', color: 'var(--text-main)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Final Sentiment Report</h4>
            
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: '16px' }}>
              {metrics.finalReport}
            </div>

            <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
              <div style={{ width: '80px', height: '80px', borderRadius: '50%', background: 'conic-gradient(#10b981 0% 45%, #f59e0b 45% 75%, #ef4444 75% 100%)', boxShadow: '0 4px 10px rgba(0,0,0,0.3)' }} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '0.8rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><div style={{ width: 8, height: 8, background: '#10b981', borderRadius: '2px' }}/> Positive 45%</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><div style={{ width: 8, height: 8, background: '#f59e0b', borderRadius: '2px' }}/> Neutral 30%</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><div style={{ width: 8, height: 8, background: '#ef4444', borderRadius: '2px' }}/> Negative 25%</div>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string, value: string }) {
  return (
    <div style={{
      background: 'rgba(0,0,0,0.2)',
      padding: '0.75rem',
      borderRadius: '8px',
      border: '1px solid rgba(255,255,255,0.05)'
    }}>
      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '4px' }}>
        {label}
      </div>
      <div className="mono" style={{ fontSize: '1.1rem', fontWeight: 'bold' }}>
        {value}
      </div>
    </div>
  );
}
