import { useEffect, useRef } from 'react';
import type{ MessageEvent, Pod } from '../services/MockDataLayer';

interface DebateFeedProps {
  messages: MessageEvent[];
  pods: Pod[];
}

export function DebateFeed({ messages, pods }: DebateFeedProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const getPodName = (id: string) => {
    return pods.find(p => p.id === id)?.name || id;
  };

  const getPodRoleColor = (id: string) => {
    const role = pods.find(p => p.id === id)?.role;
    if (role === 'judge') return 'var(--color-judge)';
    if (role === 'worker') return 'var(--color-worker)';
    if (role === 'summarizer') return 'var(--color-summarizer)';
    return 'var(--text-muted)';
  };

  let currentRound = -1;

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }} ref={scrollRef}>
      {messages.length === 0 && (
        <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '2rem', fontStyle: 'italic' }}>
          Waiting for activity...
        </div>
      )}

      {messages.map((msg, idx) => {
        const isNewRound = msg.round !== undefined && msg.round !== currentRound;
        if (isNewRound && msg.round !== undefined) {
          currentRound = msg.round;
        }

        return (
          <div key={msg.id} style={{ display: 'flex', flexDirection: 'column' }}>
            {isNewRound && (
              <div style={{
                margin: '1.5rem 0 0.5rem',
                padding: '4px 0',
                borderBottom: '1px solid rgba(255,255,255,0.1)',
                color: 'var(--text-muted)',
                fontSize: '0.8rem',
                textTransform: 'uppercase',
                letterSpacing: '1px'
              }}>
                Round {currentRound}
              </div>
            )}

            <div className="animate-slide-up" style={{
              background: 'rgba(0,0,0,0.2)',
              borderRadius: '8px',
              padding: '0.75rem',
              borderLeft: `3px solid ${getPodRoleColor(msg.senderId)}`,
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
              position: 'relative'
            }}>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '0.8rem' }}>
                  <span className="mono" style={{ color: getPodRoleColor(msg.senderId), fontWeight: 'bold' }}>
                    {getPodName(msg.senderId)}
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>→</span>
                  <span className="mono" style={{ color: getPodRoleColor(msg.recipientId) }}>
                    {getPodName(msg.recipientId)}
                  </span>
                </div>

                <span className="mono" style={{
                  fontSize: '0.7rem',
                  background: 'rgba(255,255,255,0.1)',
                  padding: '2px 6px',
                  borderRadius: '4px'
                }}>
                  {msg.type}
                </span>
              </div>

              <div style={{ fontSize: '0.9rem', color: 'var(--text-main)', lineHeight: 1.4 }}>
                {msg.excerpt}
              </div>

              {msg.referenceId && (() => {
                const refMsg = messages.find(m => m.id === msg.referenceId);
                return (
                  <div style={{ 
                    marginTop: '6px',
                    borderLeft: '2px dashed var(--color-judge)',
                    fontSize: '0.75rem',
                    color: 'var(--text-muted)',
                    fontStyle: 'italic',
                    background: 'rgba(0,0,0,0.1)',
                    padding: '6px 10px',
                    borderRadius: '0 4px 4px 0'
                  }}>
                    <span style={{fontWeight: 600}}>Referencing {getPodName(refMsg?.senderId || '')}:</span> "{refMsg?.excerpt || 'Unknown context'}"
                  </div>
                );
              })()}
            </div>
          </div>
        );
      })}
    </div>
  );
}
