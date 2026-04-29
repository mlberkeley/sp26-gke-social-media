# Multi-Agent Debate Dashboard

This is the front-end dashboard for the Multi-Agent Debate System on Google Kubernetes Engine (GKE). It provides a real-time visual interface for orchestrating and monitoring sentiment analysis workflows performed by a group of autonomous agents.

## Features

- **Live Agent Topology:** A dynamic visualization of the Judge-Worker-Summarizer workflow, showing real-time communication between agents as they coordinate tasks.
- **Chronological Debate Feed:** A live-updating feed that displays inquiries from the judge, alongside reasoning, searches, and responses from the worker agents.
- **Metrics Panel:** Displays quantitative data, agent stance rosters, and the final sentiment report once the debate is completed.

## Technologies Used

- React (with TypeScript)
- Vite
- CSS (Vanilla)

## Getting Started

To run the dashboard locally, use the following commands in your terminal:

```bash
# Install the necessary dependencies
npm install

# Start the development server
npm run dev
```

## Running the Backend

Ensure that the GKE orchestration backend (containing the `orchestrator.py` logic) is active. The backend is responsible for agent-to-agent communication via internal Kubernetes services and uses Redis for shared state coordination.