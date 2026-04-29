import { useEffect, useState } from 'react';
import { mockDataLayer, type Pod, type MessageEvent, type MetricState } from '../services/MockDataLayer';
import { AgentTopology } from './AgentTopology.tsx';
import { DebateFeed } from './DebateFeed.tsx';
import { MetricsPanel } from './MetricsPanel.tsx';

interface LiveRunModeProps {
  onReset: () => void;
}

export function LiveRunMode({ onReset }: LiveRunModeProps) {
  const [pods, setPods] = useState<Pod[]>([]);
  const [messages, setMessages] = useState<MessageEvent[]>([]);
  const [metrics, setMetrics] = useState<MetricState | null>(null);

  useEffect(() => {
    const unsubscribe = mockDataLayer.subscribe((newPods, newMessages, newMetrics) => {
      setPods(newPods);
      setMessages(newMessages);
      setMetrics(newMetrics);
    });
    return () => unsubscribe();
  }, []);

  if (!metrics) return null;

  return (
    <div style={{
      flex: 1,
      display: 'grid',
      gridTemplateColumns: 'minmax(300px, 1fr) minmax(400px, 1.2fr) minmax(300px, 1fr)',
      gap: '1rem',
      padding: '1rem',
      height: '100%',
      boxSizing: 'border-box'
    }}>
      {/* Left Panel: Agent Topology */}
      <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '1rem', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ fontSize: '1.1rem' }}>Agent Topology</h3>
          <button
            onClick={onReset}
            style={{ background: 'transparent', border: '1px solid var(--glass-border)', color: 'var(--text-muted)', borderRadius: '4px', cursor: 'pointer', padding: '4px 8px' }}
          >
            End Run
          </button>
        </div>
        <AgentTopology pods={pods} latestMessages={messages.slice(-5)} />
      </div>

      {/* Center Panel: Debate Feed */}
      <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '1rem', borderBottom: '1px solid var(--glass-border)' }}>
          <h3 style={{ fontSize: '1.1rem' }}>Debate Feed</h3>
        </div>
        <DebateFeed messages={messages} pods={pods} />
      </div>

      {/* Right Panel: Metrics */}
      <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '1rem', borderBottom: '1px solid var(--glass-border)' }}>
          <h3 style={{ fontSize: '1.1rem' }}>System Metrics</h3>
        </div>
        <MetricsPanel metrics={metrics} pods={pods} />
      </div>
    </div>
  );
}
