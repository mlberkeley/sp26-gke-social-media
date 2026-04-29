import { useState } from 'react';
import { InputMode } from './components/InputMode';
import { LiveRunMode } from './components/LiveRunMode.tsx';
import { mockDataLayer } from './services/MockDataLayer';

export type AppMode = 'input' | 'live';

function App() {
  const [mode, setMode] = useState<AppMode>('input');

  const handleRun = async (topic: string) => {
    setMode('live');
    await mockDataLayer.startRun(topic);
  };

  const handleReset = () => {
    mockDataLayer.stop();
    setMode('input');
  };

  return (
    <div id="app">
      {mode === 'input' ? (
        <InputMode onRun={handleRun} />
      ) : (
        <LiveRunMode onReset={handleReset} />
      )}
    </div>
  );
}

export default App;
