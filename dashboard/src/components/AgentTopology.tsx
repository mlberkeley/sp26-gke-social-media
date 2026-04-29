import { useMemo } from 'react';
import type{ Pod, MessageEvent, AgentRole } from '../services/MockDataLayer';

interface AgentTopologyProps {
  pods: Pod[];
  latestMessages: MessageEvent[];
}

export function AgentTopology({ pods, latestMessages }: AgentTopologyProps) {
  const judge = pods.find(p => p.role === 'judge');
  const summarizer = pods.find(p => p.role === 'summarizer');
  const workers = pods.filter(p => p.role === 'worker');

  const getRoleColor = (role: AgentRole) => {
    if (role === 'judge') return 'var(--color-judge)';
    if (role === 'worker') return 'var(--color-worker)';
    return 'var(--color-summarizer)';
  };

  const getRoleClass = (role: AgentRole) => {
    return `badge-${role}`;
  };

  const renderNode = (pod: Pod | undefined, x: number, y: number) => {
    if (!pod) return null;
    const isGlow = pod.state !== 'idle' && pod.state !== 'waiting' && pod.state !== 'complete';

    return (
      <div
        key={pod.id}
        style={{
          position: 'absolute',
          left: `${x}%`,
          top: `${y}%`,
          transform: 'translate(-50%, -50%)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '8px',
          zIndex: 10
        }}
      >
        <div
          className={`${isGlow ? 'animate-glow' : ''}`}
          style={{
            width: '60px',
            height: '60px',
            borderRadius: '50%',
            background: 'var(--bg-card)',
            border: `2px solid ${getRoleColor(pod.role)}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
            transition: 'all 0.3s ease'
          }}
        >
          <span className="mono" style={{ fontSize: '0.9rem', fontWeight: 'bold' }}>
            {pod.name.split('-')[0].substring(0, 1) + (pod.name.split('-')[1] || '')}
          </span>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div className="mono" style={{ fontSize: '0.8rem', color: 'var(--text-main)' }}>{pod.name}</div>
          <div className={`badge ${getRoleClass(pod.role)}`} style={{ marginTop: '4px', fontSize: '0.65rem' }}>
            {pod.state}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div style={{ flex: 1, position: 'relative', overflow: 'hidden', backgroundColor: 'rgba(0,0,0,0.1)' }}>
      {/* Edges SVG Layer */}
      <svg style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', zIndex: 1, pointerEvents: 'none' }}>
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2.5" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>

        {workers.map((worker, i) => {
          const startX = 50;
          const startY = 15;
          const endX = 20 + ((60) / (workers.length - 1 || 1)) * i;
          const endY = 50;

          // Check if active message
          const activeJudgeToWorker = latestMessages.find(m => m.senderId === judge?.id && m.recipientId === worker.id);
          const activeWorkerToJudge = latestMessages.find(m => m.senderId === worker.id && m.recipientId === judge?.id);

          const isActive = activeJudgeToWorker || activeWorkerToJudge;
          const strokeColor = isActive ? (activeJudgeToWorker ? getRoleColor('judge') : getRoleColor('worker')) : 'rgba(255,255,255,0.1)';

          return (
            <g key={`edge-jw-${worker.id}`}>
              <line
                x1={`${startX}%`} y1={`${startY}%`}
                x2={`${endX}%`} y2={`${endY}%`}
                stroke={strokeColor}
                strokeWidth={isActive ? 3 : 1}
                strokeDasharray={isActive ? "5, 5" : "0"}
                filter={isActive ? "url(#glow)" : ""}
              >
                {isActive && (
                  <animate attributeName="stroke-dashoffset" from="100" to="0" dur="1s" repeatCount="indefinite" />
                )}
              </line>
              {isActive && (
                <text x={`${(startX + endX)/2}%`} y={`${(startY + endY)/2 - 2}%`} fill={strokeColor} fontSize="10" className="mono" textAnchor="middle">
                  {activeJudgeToWorker?.type || activeWorkerToJudge?.type}
                </text>
              )}
            </g>
          );
        })}

        {/* Worker to Summarizer Edges */}
        {workers.map((worker, i) => {
          const startX = 20 + ((60) / (workers.length - 1 || 1)) * i;
          const startY = 50;
          const endX = 50;
          const endY = 85;

          const activeToSummarizer = latestMessages.find(m => m.senderId === worker.id && m.recipientId === summarizer?.id);
          const strokeColor = activeToSummarizer ? getRoleColor('worker') : 'rgba(255,255,255,0.05)';

          return (
            <line
              key={`edge-ws-${worker.id}`}
              x1={`${startX}%`} y1={`${startY}%`}
              x2={`${endX}%`} y2={`${endY}%`}
              stroke={strokeColor}
              strokeWidth={activeToSummarizer ? 2 : 1}
            />
          );
        })}

        {/* Judge to Summarizer direct edge */}
        {(() => {
          const activeJ2S = latestMessages.find(m => m.senderId === judge?.id && m.recipientId === summarizer?.id);
          const strokeColor = activeJ2S ? getRoleColor('judge') : 'rgba(255,255,255,0.05)';

          return (
            <g>
              <line
                x1="50%" y1="15%"
                x2="50%" y2="85%"
                stroke={strokeColor}
                strokeWidth={activeJ2S ? 2 : 1}
                strokeDasharray="4 4"
              />
              {activeJ2S && (
                <text x="52%" y="50%" fill={strokeColor} fontSize="10" className="mono">
                  {activeJ2S.type}
                </text>
              )}
            </g>
          );
        })()}

      </svg>

      {/* Nodes */}
      {renderNode(judge, 50, 15)}

      {workers.map((worker, i) => {
        const xPos = 20 + ((60) / (workers.length - 1 || 1)) * i;
        return renderNode(worker, xPos, 50);
      })}

      {renderNode(summarizer, 50, 85)}
    </div>
  );
}
