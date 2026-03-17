"""
Prompt templates for the social media sentiment analysis agent.

Each prompt is a string template with {variable} placeholders that get filled in by the
LangGraph nodes or agent modules.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Orchestrator — plans 2-4 sub-agents dynamically
# This is the ONLY hardcoded prompt for the orchestrator.
# ---------------------------------------------------------------------------
ORCHESTRATOR_PLANNING_PROMPT = """\
You are a research planning assistant. Given the topic below, design 2-4 \
concurrent research sub-agents. Each agent should cover a DIFFERENT angle \
so that together they provide comprehensive coverage.

**Topic:** {topic}

Possible ways to split work:
- By **platform**: one agent searches X/Twitter, another Reddit, another news
- By **viewpoint**: one tracks mainstream opinion, another contrarian views
- By **sub-topic**: split the topic into related sub-themes
- By **audience**: industry experts vs general public vs media

For each sub-agent, provide:
- `focus`: a short label (e.g., "X/Twitter sentiment", "Reddit deep-dive")
- `platform_hint`: preferred platform to search ("x.com", "reddit.com", \
  "news", "general"). Used to optimize search queries.
- `prompt`: specific research instructions for this agent. Be detailed — \
  tell it exactly what to look for, what angles to explore, and what kind \
  of posts/discussions to prioritize.

Return ONLY a JSON array, no commentary. Example:
[
  {{
    "focus": "X/Twitter hot takes",
    "platform_hint": "x.com",
    "prompt": "Search X/Twitter for the most viral and opinionated posts about ..."
  }},
  {{
    "focus": "Reddit technical discussion",
    "platform_hint": "reddit.com",
    "prompt": "Search Reddit for in-depth technical discussions and debates about ..."
  }}
]
"""

# ---------------------------------------------------------------------------
# Synthesizer — merges results from multiple researchers into one report
# ---------------------------------------------------------------------------
SYNTHESIZER_PROMPT = """\
You are a senior social media intelligence analyst. Multiple research agents \
have independently gathered and analyzed data about the topic below. Your job \
is to synthesize their findings into a single, unified sentiment report.

**Topic:** {topic}
**Timestamp:** {timestamp}

**Research Results from {agent_count} Agents:**
{all_results}

## Report Requirements

Produce the report in **Markdown** with the following sections. Cross-reference \
findings across agents, resolve contradictions, and highlight consensus.

### 📊 Executive Summary
- 2-3 sentence overview of overall sentiment and why it matters
- Note the breadth of sources (which platforms/angles were covered)

### 🔥 Key Findings
- 3-5 most important takeaways, synthesized across all agents
- Flag where agents agreed vs disagreed

### 📈 Sentiment Breakdown
- Aggregated sentiment distribution across all sources
- Compare sentiment by platform/angle if notable differences exist

### 💬 Notable Voices & Opinions
- Highlight 5-7 specific posts or viewpoints from across all agents
- Include source platform for each

### 🔀 Trending Sub-topics
- Merged view of what people are discussing
- Note sub-topics that appeared across multiple agents

### ⚡ Contrarian & Minority Views
- Dissenting opinions found by any agent
- Cross-platform contrarian views are especially noteworthy

### 🔮 Outlook & Emerging Narratives
- Synthesized direction of sentiment
- Are different platforms showing different trends?

### 📋 Methodology Note
- Which agents covered which area
- Total sources analyzed

---

Write the report NOW. Be specific, data-driven, and insightful. Avoid filler \
language. Every sentence should add value. Highlight cross-platform patterns.
"""

# ---------------------------------------------------------------------------
# Node 1 — research_topic
# this node uses Tavily to search for data from X
# ---------------------------------------------------------------------------
SEARCH_QUERIES_PROMPT = """\
You are a social media research assistant. Your job is to generate exactly 3 \
highly effective web search queries that will surface recent posts, threads, \
and discussions from X (Twitter) and other social platforms about the topic \
below.

**Topic:** {topic}

Requirements for the queries:
1. One query MUST include "site:x.com" or "site:twitter.com" to target X posts.
2. One query should target broader social media discussion (Reddit, Mastodon, \
   Bluesky, or news reactions).
3. One query should focus on sentiment or opinions (include words like \
   "opinion", "think", "reaction", "feel", "hot take").
4. All queries should bias toward RECENT content (include "2026" or "today" \
   or "this week" where natural).

Return ONLY a JSON array of 3 strings, no commentary. Example:
["query one", "query two", "query three"]
"""

# ---------------------------------------------------------------------------
# Node 2 — analyze_sentiment
# this node uses llm of choice (currently openAI, see sentiment_agent.py) to analyze raw results from node 1
# ---------------------------------------------------------------------------
SENTIMENT_ANALYSIS_PROMPT = """\
You are an expert social media sentiment analyst. Below are raw search results \
gathered from X (Twitter) and other social platforms about this topic:

**Topic:** {topic}

**Raw search results:**
{search_results}

Analyze these results deeply. For each distinct viewpoint or post you can \
identify, extract:
- The **stance** (positive / negative / neutral / mixed)
- The **emotional tone** (excited, angry, fearful, hopeful, sarcastic, etc.)
- The **intensity** (1-5 scale, where 1=mild, 5=extreme)
- A **brief summary** of what was said
- The **source** if identifiable (username, platform)

Also identify:
- **Dominant sentiment** across all posts
- **Key themes** and **sub-topics** people are discussing
- **Notable contrarian views** (minority opinions that stand out)
- **Emerging narratives** (new angles or framings gaining traction)

Return your analysis as structured JSON with these sections:
{{
  "overall_sentiment": "positive|negative|neutral|mixed",
  "confidence": 0.0-1.0,
  "dominant_emotions": ["emotion1", "emotion2"],
  "post_analyses": [
    {{
      "summary": "...",
      "stance": "...",
      "emotion": "...",
      "intensity": 1-5,
      "source": "..."
    }}
  ],
  "key_themes": ["theme1", "theme2"],
  "contrarian_views": ["view1", "view2"],
  "emerging_narratives": ["narrative1", "narrative2"]
}}
"""

# ---------------------------------------------------------------------------
# Node 3 — generate_report
# this node uses llm of choice (currently openAI, see sentiment_agent.py) to produce structured sentiment report
# ---------------------------------------------------------------------------
REPORT_GENERATION_PROMPT = """\
You are a senior social media intelligence analyst producing a sentiment \
report for stakeholders. Using the structured sentiment analysis below, \
write a comprehensive yet scannable report.

**Topic:** {topic}
**Timestamp:** {timestamp}

**Sentiment Analysis Data:**
{sentiment_analysis}

## Report Requirements

Produce the report in **Markdown** with the following sections. Be specific, \
cite examples from the data, and use concrete language rather than vague \
generalizations.

### 📊 Executive Summary
- 2-3 sentence overview of overall sentiment and why it matters
- Include the dominant sentiment direction and confidence level

### 🔥 Key Findings
- Bullet points of the 3-5 most important takeaways
- Each finding should be actionable or insightful

### 📈 Sentiment Breakdown
- Distribution of positive/negative/neutral/mixed opinions
- Average emotional intensity
- Most common emotions detected

### 💬 Notable Voices & Opinions
- Highlight 3-5 specific posts or viewpoints that best represent the discourse
- Include direct quotes or paraphrases where available
- Note any influential accounts or viral posts

### 🔀 Trending Sub-topics
- What specific aspects of the main topic are people focusing on?
- Any unexpected tangents or related discussions?

### ⚡ Contrarian & Minority Views
- What are the dissenting opinions?
- Why might these matter despite being in the minority?

### 🔮 Outlook & Emerging Narratives
- What direction is sentiment heading?
- Any early signals of shifting opinion?
- New framings or narratives gaining traction

### 📋 Methodology Note
- Brief note on data sources (X/Twitter, social media, web) and search scope

---

Write the report NOW. Be specific, data-driven, and insightful. Avoid filler \
language. Every sentence should add value.
"""

# ---------------------------------------------------------------------------
# Researcher — search query generation (adapted to use focus/platform hints)
# ---------------------------------------------------------------------------
RESEARCHER_SEARCH_QUERIES_PROMPT = """\
You are a social media research assistant. Your job is to generate exactly 3 \
highly effective web search queries that will surface recent posts, threads, \
and discussions about the topic below.

**Topic:** {topic}
**Your Focus Area:** {focus}
**Preferred Platform:** {platform_hint}

Requirements for the queries:
1. At least one query MUST include "site:{platform_hint}" to target that platform.
2. One query should capture broader discussion beyond the primary platform.
3. One query should focus on sentiment or opinions (include words like \
   "opinion", "think", "reaction", "feel", "hot take").
4. All queries should bias toward RECENT content (include "2026" or "today" \
   or "this week" where natural).
5. Queries should be specific to your assigned focus area.

Return ONLY a JSON array of 3 strings, no commentary. Example:
["query one", "query two", "query three"]
"""
