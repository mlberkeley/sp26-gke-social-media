export type AgentRole = 'judge' | 'worker' | 'summarizer';
export type AgentState = 'idle' | 'planning' | 'researching' | 'advocating' | 'waiting' | 'responding' | 'complete';
export type MessageType = 'TASK' | 'INTERROGATE' | 'REBUTTAL' | 'RESULT';

export interface Pod {
  id: string;
  name: string;
  role: AgentRole;
  state: AgentState;
  stance?: string;
  divergence?: number;
}

export interface MessageEvent {
  id: string;
  timestamp: Date;
  senderId: string;
  recipientId: string;
  type: MessageType;
  excerpt: string;
  round?: number;
  referenceId?: string; // ID of a previous message it refers to
}

export interface MetricState {
  tokensUsed: number;
  tavilyCalls: number;
  activeWorkers: number;
  roundsCompleted: number;
  maxRounds: number;
  timeElapsed: number; // in seconds
  estimatedCost: number; // in USD
  confidence: number[]; // Trend over rounds
  finalSentiment?: { label: string; value: number }[];
  finalReport?: string;
}

export type DebateStateListener = (pods: Pod[], messages: MessageEvent[], metrics: MetricState) => void;

export class MockDataLayer {
  private pods: Pod[] = [];
  private messages: MessageEvent[] = [];
  private metrics: MetricState;
  private listeners: DebateStateListener[] = [];
  private timer: number | null = null;
  private topic: string = '';

  constructor() {
    this.metrics = this.getInitialMetrics();
  }

  private getInitialMetrics(): MetricState {
    return {
      tokensUsed: 0,
      tavilyCalls: 0,
      activeWorkers: 0,
      roundsCompleted: 0,
      maxRounds: 3,
      timeElapsed: 0,
      estimatedCost: 0,
      confidence: [0.3],
    };
  }

  subscribe(listener: DebateStateListener) {
    this.listeners.push(listener);
    listener(this.pods, this.messages, this.metrics);
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener);
    };
  }

  private notify() {
    this.listeners.forEach(l => l([...this.pods], [...this.messages], { ...this.metrics }));
  }

  private updatePod(id: string, updates: Partial<Pod>) {
    const pod = this.pods.find(p => p.id === id);
    if (pod) {
      Object.assign(pod, updates);
      this.notify();
    }
  }

  private addMessage(msg: Omit<MessageEvent, 'id' | 'timestamp'>) {
    const id = `msg-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
    const fullMsg: MessageEvent = { ...msg, id, timestamp: new Date() };
    this.messages.push(fullMsg);

    // Simulate cost/token increment per message
    this.metrics.tokensUsed += Math.floor(Math.random() * 500) + 100;
    this.metrics.estimatedCost = Number((this.metrics.tokensUsed * 0.000001).toFixed(4));

    this.notify();
    return id;
  }

  async startRun(topic: string, numWorkers: number = 3) {
    this.topic = topic;
    this.metrics = this.getInitialMetrics();
    this.messages = [];

    // Initialize Pods
    this.pods = [
      { id: 'judge-0', name: 'Judge-Main', role: 'judge', state: 'idle' }
    ];

    const stances = ['Strong Pro', 'Neutral/Nuanced', 'Strong Anti', 'Devil\'s Advocate'];

    for (let i = 1; i <= numWorkers; i++) {
      this.pods.push({
        id: `worker-${i}`,
        name: `Worker-${i}`,
        role: 'worker',
        state: 'idle',
        stance: stances[(i - 1) % stances.length],
        divergence: Math.random() // Random initial divergence
      });
    }

    this.pods.push({ id: 'summarizer-0', name: 'Summarizer-Final', role: 'summarizer', state: 'idle' });
    this.notify();

    // Start elapsed time ticker
    const startTime = Date.now();
    this.timer = window.setInterval(() => {
      this.metrics.timeElapsed = Math.floor((Date.now() - startTime) / 1000);
      this.notify();
    }, 1000);

    // Simulate Workflow
    await this.delay(1000);
    this.updatePod('judge-0', { state: 'planning' });
    await this.delay(1500);

    // Judge spawns workers
    for (let i = 1; i <= numWorkers; i++) {
      this.addMessage({
        senderId: 'judge-0',
        recipientId: `worker-${i}`,
        type: 'TASK',
        excerpt: `Research sub-topic of: "${topic}" from stance: ${this.pods[i].stance}`
      });
    }

    this.metrics.activeWorkers = numWorkers;
    this.updatePod('judge-0', { state: 'waiting' });
    for (let i = 1; i <= numWorkers; i++) {
      this.updatePod(`worker-${i}`, { state: 'researching' });
      this.metrics.tavilyCalls += Math.floor(Math.random() * 3) + 1;
    }

    await this.delay(2500);

    // Interrogation rounds
    for (let round = 1; round <= this.metrics.maxRounds; round++) {
      this.metrics.roundsCompleted = round - 1;
      this.notify();

      const prevAnswers: string[] = [];

      for (let i = 1; i <= numWorkers; i++) {
        this.updatePod(`worker-${i}`, { state: 'advocating' });
        await this.delay(800 + Math.random() * 1000);

        const ansId = this.addMessage({
          senderId: `worker-${i}`,
          recipientId: 'judge-0',
          type: 'RESULT',
          round,
          excerpt: `Draft argument (Round ${round}) compiled.`
        });
        prevAnswers.push(ansId);
        this.updatePod(`worker-${i}`, { state: 'waiting' });
      }

      await this.delay(1500);
      this.updatePod('judge-0', { state: 'planning' });

      // Judge questions workers
      for (let i = 1; i <= numWorkers; i++) {
        await this.delay(800);
        const stance = this.pods[i].stance || '';
        let inquiry = 'Can you clarify your point regarding the third finding?';
        if (stance.includes('Pro')) inquiry = `Could you expand on the positive externalities you mentioned regarding ${topic}?`;
        else if (stance.includes('Anti')) inquiry = `I need clarification on the worst-case risk vectors you identified for ${topic}.`;
        else if (stance.includes('Nuanced')) inquiry = `Which of the conflicting metrics should we weigh more heavily here?`;
        else if (stance.includes('Advocate')) inquiry = `Assume your counter-argument is flawed; what is the strongest counter-counter-argument?`;

        this.addMessage({
          senderId: 'judge-0',
          recipientId: `worker-${i}`,
          type: 'INTERROGATE',
          round,
          excerpt: inquiry,
          referenceId: prevAnswers[i-1]
        });
        this.updatePod(`worker-${i}`, { state: 'responding' });
      }

      await this.delay(2000);
      // Workers reply
      for (let i = 1; i <= numWorkers; i++) {
        await this.delay(500);
        this.addMessage({
          senderId: `worker-${i}`,
          recipientId: 'judge-0',
          type: 'REBUTTAL',
          round,
          excerpt: `Based on additional data, here is the clarification.`
        });
        this.updatePod(`worker-${i}`, { state: 'waiting' });

        // Update divergence after reply
        this.updatePod(`worker-${i}`, { divergence: Math.random() * 0.5 });
      }

      // Update confidence
      this.metrics.confidence.push(Math.min(1.0, this.metrics.confidence[this.metrics.confidence.length - 1] + 0.15 + Math.random() * 0.1));
      this.metrics.roundsCompleted = round;
    }

    // Final Summarization
    this.updatePod('judge-0', { state: 'planning' });
    await this.delay(2000);
    this.addMessage({
      senderId: 'judge-0',
      recipientId: 'summarizer-0',
      type: 'TASK',
      excerpt: `Synthesize final findings.`
    });
    this.updatePod('judge-0', { state: 'complete' });
    this.updatePod('summarizer-0', { state: 'researching' });
    this.metrics.activeWorkers = 0;

    await this.delay(3000);
    this.addMessage({
      senderId: 'summarizer-0',
      recipientId: 'judge-0', // Or abstract "System"
      type: 'RESULT',
      excerpt: `Final consensus report generated.`
    });
    this.updatePod('summarizer-0', { state: 'complete' });
    for (let i = 1; i <= numWorkers; i++) {
      this.updatePod(`worker-${i}`, { state: 'complete' });
    }

    // Stop timer and set final states
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }

    this.metrics.finalSentiment = [
      { label: 'Positive', value: 45 },
      { label: 'Neutral', value: 30 },
      { label: 'Negative', value: 25 },
    ];
    this.metrics.finalReport = `The Multi-Agent Debate on "${this.topic}" has concluded. The panel reached a consensus with a moderate positive skew (45%). Key agreements highlighted the long-term benefits, while valid concerns raised by dissenting agents warrant structured regulation. Confidence stands at ${(this.metrics.confidence[this.metrics.confidence.length - 1] * 100).toFixed(0)}%.`;
    this.notify();
  }

  stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  private delay(ms: number) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

export const mockDataLayer = new MockDataLayer();
