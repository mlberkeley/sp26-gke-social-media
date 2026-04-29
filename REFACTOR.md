# **Social Media Sentiment Analysis Agent Orchestration Spec**

## **1\. Purpose**

Build a multi-agent system on **Google Kubernetes Engine (GKE)** that analyzes sentiment around a topic on social media, then produces a structured report showing the major positions, the debate axes, the crossovers, the antagonisms, and which side has the stronger case on each argument.

The system uses:

- **ADK** for agent implementation
- **A2A** for agent-to-agent communication
- **OpenAI API** as the LLM backend for all agents
- **Tavily** for web/search grounding
- **GKE Standard** as the runtime

---

## **2\. Core Design Decisions**

### **2.1 Agent roles**

There are three logical roles:

1. **Judge Agent**
   - Orchestrates the run
   - Decides how many worker agents to spawn
   - Assigns stances
   - Interrogates workers
   - Aggregates all evidence and arguments
   - Invokes the summarizer
2. **Worker Agent**
   - A single pod that internally performs both:
     - **Researcher** behavior
     - **Advocate** behavior
   - The researcher side gathers evidence and identifies the strongest arguments for the assigned stance
   - The advocate side turns that research into a persuasive defense of the stance
3. **Summarizer Agent**
   - Takes the judge’s aggregate output and produces the final polished report

### **2.2 Pod boundaries**

- The **judge** runs in its own pod and deployment.
- Each **worker** runs in its own pod.
- The **summarizer** runs in its own pod.

Even though researcher and advocate are conceptually distinct, they are implemented together in the same worker pod.

### **2.3 Storage policy**

Use **Redis only**.

### **2.4 Network policy**

There are **no external IPs for individual containers**. All agent communication must happen internally inside the cluster using Kubernetes Services and cluster DNS.

### **2.5 Search policy**

Use **Tavily** for search grounding in two places:

- The **judge** uses Tavily during planning to estimate how broad or fragmented the topic is and to decide how many workers to spawn.
- Each **worker** uses Tavily during research to gather supporting evidence, counterarguments, and examples for its assigned stance.

---

## **3\. Recommended Technology Stack**

### **3.1 Infrastructure**

- **GKE Standard**
- **Artifact Registry** for container images
- **Cloud Build** for building images
- **Cloud Deploy** for promotion between environments
- **Workload Identity Federation for GKE** for GCP authentication from pods
- **Redis** for coordination and run artifacts

### **3.2 Agent/runtime libraries**

- **ADK** for agent logic and orchestration
- **A2A** for inter-agent communication
- **OpenAI API** for model inference
- **Tavily API** for search/retrieval

### **3.3 Kubernetes primitives**

- **Deployments** for judge and summarizer
- **Jobs** for workers
- **Services of type ClusterIP** for all agent endpoints
- **NetworkPolicies** to restrict lateral access
- **Secrets** for API keys
- **ConfigMaps** for prompts and static settings

---

## **4\. Why Redis Only**

Redis is used as the single shared coordination layer.

### **What Redis stores**

1. **Run metadata**
   - `run_id`
   - topic
   - status
   - timestamps
   - spawned stance list
   - worker roster
2. **Agent outputs**
   - raw worker results
   - judge intermediate summaries
   - final summarizer output
3. **Task state**
   - pending / running / complete / failed
   - worker heartbeats if desired
   - retries
   - cancellation flags
4. **Temporary coordination structures**
   - locks
   - queues
   - per-run maps
   - dedupe keys

### **Where outputs go**

#### **Judge output**

The judge writes its intermediate and aggregate state to Redis, keyed by run:

- `run:{run_id}:judge:plan`
- `run:{run_id}:judge:interrogation`
- `run:{run_id}:judge:aggregate`

#### **Worker output**

Each worker writes a single structured JSON result to Redis:

- `run:{run_id}:worker:{worker_id}:result`
- `run:{run_id}:worker:{worker_id}:status`

#### **Summarizer output**

The summarizer writes the final report to Redis:

- `run:{run_id}:final_report`
- `run:{run_id}:final_report_md`

---

## **5\. Kubernetes and Service Topology**

### **5.1 Namespaces**

Use separate namespaces:

- `judge`
- `workers`
- `summarizer`
- `system`

### **5.2 Judge**

**Type:** Deployment

The judge is a long-running service that accepts a topic and controls the full workflow.

### **5.3 Workers**

**Type:** Kubernetes Job

Each spawned worker is a one-off job that handles exactly one stance for exactly one run.

### **5.4 Summarizer**

**Type:** Kubernetes Job

The summarizer runs after worker aggregation is complete.

### **5.5 Internal exposure for A2A**

Because there are no external IPs, every agent exposes its A2A endpoint through a **ClusterIP Service**.

Use internal service DNS names such as:

- `judge.judge.svc.cluster.local`
- `worker-<run-id>-<stance>.workers.svc.cluster.local`
- `summarizer.summarizer.svc.cluster.local`

Kubernetes services of type **ClusterIP** provide a stable internal IP for internal clients, and GKE service discovery maps service names to those IPs through cluster DNS. That is the right exposure mechanism for A2A inside the cluster.

### **5.6 A2A endpoint shape**

Each agent should expose:

- `/.well-known/agent-card.json`
- `POST /a2a/messages` or the framework’s equivalent message endpoint
- `GET /a2a/tasks/{task_id}`
- `POST /a2a/tasks/{task_id}/cancel`

The exact path implementation can follow the ADK/A2A library defaults, but the service must advertise a resolvable internal URL in its Agent Card.

### **5.7 Worker service pattern**

For each worker Job:

1. Create a dedicated **ClusterIP Service**.
2. Label the worker pod with the run/stance identifiers.
3. Point the Service selector at that pod.
4. Let the judge call the worker over internal DNS.

This avoids any need for external ingress, load balancers, or public IPs.

### **5.8 Network policy**

Allow:

- judge → workers
- judge → summarizer
- all agents → Redis
- all agents → Tavily API egress
- all agents → OpenAI API egress

Deny:

- worker → worker lateral traffic
- unsolicited inbound traffic from outside the namespace boundaries

---

## **6\. A2A Communication Model**

A2A is used as the agent communication layer.

### **Judge to worker interaction**

The judge acts as the A2A client and each worker acts as an A2A server.

The worker publishes an Agent Card describing:

- name
- description
- capabilities
- preferred endpoint URL
- supported transport

The judge uses that card to send tasks and fetch task state.

### **Judge to summarizer interaction**

The summarizer is also an A2A server. The judge sends the aggregate run object to the summarizer and retrieves the polished final report.

### **Why A2A works without external IPs**

A2A only needs a reachable HTTP endpoint, not a public endpoint. In this design, the endpoint is reachable through internal cluster DNS and ClusterIP Services, so the judge can talk to workers and the summarizer entirely inside GKE.

---

## **7\. Run Lifecycle**

### **Step 1: Topic intake**

The user submits a topic.

Example:

- “Taylor Swift social sentiment right now”
- “Sentiment around the new policy announcement”

The judge creates a `run_id`.

### **Step 2: Judge planning with Tavily**

The judge performs a short Tavily search pass to estimate:

- how much conversation exists
- whether the conversation is polarized
- what the major axes of disagreement are
- how many workers to spawn

The judge should use a small, bounded search budget so planning stays fast.

### **Step 3: Determine worker roster**

The judge outputs a stance plan such as:

- positive
- negative
- mixed
- skeptical
- partisan subgroups
- niche/fringe positions

The exact number of workers is dynamic and can vary by topic.

### **Step 4: Spawn workers**

For each stance, the judge creates a worker Job and a matching internal ClusterIP Service.

Each worker receives:

- `RUN_ID`
- `STANCE_ID`
- `STANCE_LABEL`
- `TOPIC`
- Redis connection info
- OpenAI credentials
- Tavily credentials

### **Step 5: Worker research phase**

The worker first behaves like a researcher:

- uses Tavily search
- gathers evidence
- identifies dominant arguments
- finds rebuttals against the stance
- identifies supporting communities or audience clusters

### **Step 6: Worker advocate phase**

The same worker then behaves like an advocate:

- strengthens the stance
- packages evidence into a persuasive argument set
- anticipates judge questions
- identifies what would most damage its side

### **Step 7: Worker output**

The worker writes a structured JSON result to Redis and marks itself complete.

### **Step 8: Judge interrogation**

The judge asks each worker targeted questions such as:

- How popular is your stance?
- What is your strongest point?
- This other agent said \[something\], what do you have to say to that?
- What do you think of \[this piece of evidence\]?

It should make decisions on what to ask each agent and in what order based on how it feels the debate is evolving. Note that the research agents do not see each others’ outputs directly.

Judge determines after each round of interrogation (on a specific topic) if there is a clear winner → if not, keeps prompting agents for refutation/rebuttal args → max number of rounds of debate for a specific argument/point is a specific parameter to prevent endless loop of debate.

### **Step 9: Judge aggregation**

When it is satisfied, the judge combines all worker results into a single run-level intermediate object.

### **Step 10: Summarizer**

The judge sends the aggregate object to the summarizer.

### **Step 11: Final report**

The summarizer writes the polished final report to Redis and returns the rendered report.

---

## **8\. Output Schemas**

### **8.1 Worker output**

Each worker must return structured JSON, not freeform prose.

{
"run_id": "...",
"stance_id": "...",
"stance_label": "positive | negative | mixed | fringe | other",
"summary": "...",
"top_claims": \[
{
"claim": "...",
"supporting_evidence": \["..."\],
"rebuttals": \["..."\],
"confidence": 0.0,
"popularity_estimate": "low | medium | high"
}
\],
"crossover_positions": \["..."\],
"antagonistic_positions": \["..."\],
"fringe_positions": \["..."\],
"consensus_points": \["..."\],
"axes_of_debate": \["..."\],
"key_sources": \["..."\],
"confidence": 0.0
}

### **8.2 Judge aggregate output**

{
"run_id": "...",
"topic": "...",
"stances": \["..."\],
"controversy_level": "low | medium | high",
"agreement_matrix": \[\],
"rebuttal_graph": \[\],
"shared_ground": \[\],
"fringe_positions": \[\],
"conversation_locus_shift": "...",
"judge_notes": "..."
}

### **8.3 Final report output**

The summarizer should produce:

- structured JSON for machine use
- markdown for human reading

The markdown report should include:

- TOPIC
- DEGREE OF CONTROVERSY
- POSITIVE POSITIONS
- NEGATIVE POSITIONS
- ANALYSIS
- POSITIONS THAT HAVE CROSSOVER
- ANTAGONISTIC POSITIONS
- RECOGNIZED SOCIAL COHESION
- HAS THE LOCUS OF CONVERSATION CHANGED OVER TIME?
- FRINGE POSITIONS
- CONSENSUS
- AXES OF DEBATE

---

## **9\. Agent Prompts and Behavior**

### **9.1 Judge prompt behavior**

The judge must:

- stay neutral
- identify the debate structure
- decide how many workers to spawn
- ask probing questions
- prevent the system from collapsing into one-sided summaries
- prefer structured outputs

### **9.2 Worker prompt behavior**

Each worker must internally split into two phases:

#### **Researcher phase**

- skeptical evidence gathering
- Tavily search
- extraction of facts, claims, and communities
- identification of opposing arguments

#### **Advocate phase**

- defend assigned stance
- steelman the stance
- organize the argument into a persuasive case
- prioritize clarity and internal consistency

The worker should not claim certainty where it does not have it.

### **9.3 Summarizer prompt behavior**

The summarizer must:

- compress the judge’s verbose aggregate output
- preserve the actual argumentative structure
- avoid inventing new claims
- produce a clean final report

---

## **10\. Redis Key Design**

Recommended key schema:

- `run:{run_id}:meta`
- `run:{run_id}:judge:plan`
- `run:{run_id}:judge:aggregate`
- `run:{run_id}:worker:{worker_id}:status`
- `run:{run_id}:worker:{worker_id}:result`
- `run:{run_id}:summarizer:status`
- `run:{run_id}:final_report`
- `run:{run_id}:final_report_md`

Use Redis hashes or JSON values consistently. Pick one canonical representation and stick to it.

---

## **11\. Security and Secrets**

### **Secrets**

Store in Kubernetes Secrets:

- OpenAI API key
- Tavily API key
- Redis auth, if enabled

### **Identity**

Use Workload Identity Federation for GKE so workloads can authenticate to Google Cloud without service account keys.

### **Access rules**

- Judge can create and read worker state.
- Workers can write only their own result keys.
- Summarizer can read the aggregate and write the final report.

---

## **12\. Deployment Model**

### **Build pipeline**

1. Developer pushes code
2. Cloud Build builds the container images
3. Images are pushed to Artifact Registry
4. Cloud Deploy promotes them to GKE

### **Runtime deployment**

- Judge deployment is updated first
- Then worker/summarizer images are rolled out by the judge using Kubernetes API
- Redis remains separate and persistent

---

## **13\. What the Codebase Should Contain**

### **Services**

- judge service
- worker service template
- summarizer service

### **Infrastructure files**

- Dockerfiles
- Kubernetes manifests
- Services
- Jobs
- NetworkPolicies
- Secrets templates
- Redis connection configuration

### **Application code**

- OpenAI wrapper
- Tavily wrapper
- A2A server/client wrapper
- Redis state manager
- Judge planner
- Worker research/advocate pipeline
- Summarizer pipeline

---

## **14\. Implementation Priorities**

Build in this order:

1. Judge service with a single worker
2. Worker Job with Redis output
3. Internal A2A via ClusterIP Service
4. Multiple workers from dynamic stance planning
5. Summarizer Job
6. Final report formatting

---

## **16\. Non-Negotiables**

- Judge is separate from workers
- Researcher and advocate are one pod, one worker agent
- Summarizer is always present
- Redis is the only shared persistence layer
- No external IPs per container
- Tavily is used by both judge and workers
- OpenAI is the LLM backend (will be changed later on so keep it generalizable)
- A2A runs over internal Kubernetes Services only
