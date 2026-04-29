"""
Prompt templates for the judge/worker/summarizer agent system.

Each prompt is a string template with {{variable}} placeholders.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Judge — planning phase (uses Tavily results to decide stances)
# ---------------------------------------------------------------------------
JUDGE_PLANNING_PROMPT = """\
You are a neutral judge planning a structured debate analysis. You have just \
performed a preliminary search on the topic below. Using these search results, \
determine:
1. How much conversation exists around this topic
2. Whether the conversation is polarized
3. What the major axes of disagreement are
4. How many worker agents to spawn (2-6) and what stance each should defend

**Topic:** {topic}

**Preliminary search results:**
{search_results}

Return ONLY valid JSON matching this schema — no commentary:
{{
  "conversation_breadth": "narrow | moderate | broad",
  "is_polarized": true/false,
  "major_axes": ["axis1", "axis2", ...],
  "stances": [
    {{
      "stance_id": "positive",
      "stance_label": "positive",
      "description": "Defend the view that ..."
    }},
    {{
      "stance_id": "negative",
      "stance_label": "negative",
      "description": "Defend the view that ..."
    }}
  ]
}}

Possible stance labels: positive, negative, mixed, skeptical, fringe, or any \
descriptive label for partisan subgroups or niche positions. Each stance \
description should be specific enough that a worker agent knows exactly what \
position to research and defend.
"""

JUDGE_PLANNING_SEARCH_QUERIES_PROMPT = """\
You are planning a sentiment debate analysis. Generate exactly 2 search queries \
to quickly estimate how broad, polarized, and fragmented the public conversation \
is around this topic. These are for planning only — keep them broad.

**Topic:** {topic}

Return ONLY a JSON array of 2 strings, no commentary.
["query one", "query two"]
"""

# ---------------------------------------------------------------------------
# Judge — interrogation phase
# ---------------------------------------------------------------------------
JUDGE_INTERROGATION_PROMPT = """\
You are a neutral judge interrogating worker agents who have each defended a \
specific stance on a topic. You have access to all their initial outputs. Your \
goal is to probe weaknesses, find contradictions, and determine which side has \
the stronger case on each point of debate.

**Topic:** {topic}

**Worker outputs:**
{worker_outputs}

**Previous interrogation exchanges (if any):**
{previous_exchanges}

Generate targeted questions for specific workers. For each question, explain \
which worker it targets and why you are asking it. Consider:
- How popular is your stance?
- What is your strongest point?
- Worker X said [something], what do you have to say to that?
- What do you think of [this piece of evidence]?
- What would most damage your side's argument?

Return ONLY valid JSON — an array of objects:
[
  {{
    "target_worker_id": "stance_id",
    "question": "Your question here",
    "reason": "Why you are asking this"
  }}
]

Generate 1-3 questions per round. Focus on the most productive lines of inquiry.
"""

JUDGE_SHOULD_CONTINUE_PROMPT = """\
You are a neutral judge deciding whether to continue interrogating workers or \
whether the debate on each axis has reached a clear enough conclusion.

**Topic:** {topic}
**Round:** {round_number} of max {max_rounds}

**All interrogation exchanges so far:**
{all_exchanges}

**Worker outputs:**
{worker_outputs}

For each axis of debate, assess whether there is a clear winner or whether \
further interrogation would be productive. Return ONLY valid JSON:
{{
  "should_continue": true/false,
  "reason": "Brief explanation of why to continue or stop"
}}
"""

# ---------------------------------------------------------------------------
# Judge — aggregation phase
# ---------------------------------------------------------------------------
JUDGE_AGGREGATION_PROMPT = """\
You are a neutral judge producing the final aggregate analysis. You have the \
original worker outputs and all interrogation exchanges. Synthesize everything \
into a structured aggregate.

**Topic:** {topic}

**Worker outputs:**
{worker_outputs}

**Interrogation log:**
{interrogation_log}

Return ONLY valid JSON matching this schema:
{{
  "stances": ["stance1", "stance2", ...],
  "controversy_level": "low | medium | high",
  "agreement_matrix": [
    {{"stance_a": "...", "stance_b": "...", "agrees_on": ["..."], "disagrees_on": ["..."]}}
  ],
  "rebuttal_graph": [
    {{"from_stance": "...", "to_stance": "...", "rebuttal": "...", "strength": "weak | moderate | strong"}}
  ],
  "shared_ground": ["points all or most stances agree on"],
  "fringe_positions": ["positions held by very few"],
  "conversation_locus_shift": "Has the conversation changed over time? How?",
  "judge_notes": "Your overall assessment of the debate quality and conclusions"
}}
"""

# ---------------------------------------------------------------------------
# Worker — research phase
# ---------------------------------------------------------------------------
WORKER_RESEARCH_QUERIES_PROMPT = """\
You are a research agent assigned to gather evidence for a specific stance on \
a topic. Generate exactly 3 search queries that will find supporting evidence, \
counterarguments, community sentiment, and notable voices for your stance.

**Topic:** {topic}
**Your Stance:** {stance_label} — {stance_description}

Requirements:
1. One query should find supporting evidence for your stance
2. One query should find counterarguments against your stance
3. One query should identify communities or audiences that hold your stance

Return ONLY a JSON array of 3 strings, no commentary.
["query one", "query two", "query three"]
"""

WORKER_RESEARCH_ANALYSIS_PROMPT = """\
You are a skeptical researcher analyzing search results to build evidence for \
a specific stance. Extract facts, claims, community patterns, and opposing \
arguments. Be thorough but honest about the strength of evidence.

**Topic:** {topic}
**Your Stance:** {stance_label} — {stance_description}

**Search results:**
{search_results}

Analyze the results and return ONLY valid JSON:
{{
  "supporting_evidence": ["evidence1", "evidence2", ...],
  "counterarguments": ["counter1", "counter2", ...],
  "community_patterns": ["pattern1", "pattern2", ...],
  "key_sources": ["source1", "source2", ...],
  "evidence_strength": "weak | moderate | strong",
  "raw_claims": [
    {{
      "claim": "...",
      "source": "...",
      "supports_stance": true/false
    }}
  ]
}}
"""

# ---------------------------------------------------------------------------
# Worker — advocate phase
# ---------------------------------------------------------------------------
WORKER_ADVOCATE_PROMPT = """\
You are an advocate building the strongest possible case for your assigned \
stance. Using the research findings below, construct a persuasive defense. \
Steelman your position. Organize arguments by strength. Anticipate and \
preemptively address the strongest counterarguments. Do not claim certainty \
where evidence is weak.

**Topic:** {topic}
**Your Stance:** {stance_label} — {stance_description}

**Research findings:**
{research_findings}

Return ONLY valid JSON matching this schema:
{{
  "summary": "2-3 sentence summary of your stance and why it is compelling",
  "top_claims": [
    {{
      "claim": "The specific claim",
      "supporting_evidence": ["evidence1", "evidence2"],
      "rebuttals": ["preemptive rebuttal to likely counterarguments"],
      "confidence": 0.0-1.0,
      "popularity_estimate": "low | medium | high"
    }}
  ],
  "crossover_positions": ["positions where your stance overlaps with others"],
  "antagonistic_positions": ["positions directly opposed to your stance"],
  "fringe_positions": ["unusual or minority sub-positions within your stance"],
  "consensus_points": ["things even opponents would agree with"],
  "axes_of_debate": ["the key dimensions along which this debate plays out"],
  "confidence": 0.0-1.0
}}

Rank top_claims from strongest to weakest. Include 3-7 claims.
"""

# ---------------------------------------------------------------------------
# Worker — interrogation response
# ---------------------------------------------------------------------------
WORKER_INTERROGATION_RESPONSE_PROMPT = """\
You are a worker agent defending the "{stance_label}" stance on a topic. The \
judge has asked you a question during the interrogation phase. Answer honestly \
but persuasively. If you cannot defend a point, acknowledge the weakness rather \
than fabricating evidence.

**Topic:** {topic}
**Your Stance:** {stance_label}
**Your Original Output:**
{worker_output}

**Judge's Question:**
{question}

Respond with a clear, focused answer. Be specific and reference evidence from \
your research where possible.
"""

# ---------------------------------------------------------------------------
# Summarizer — final report
# ---------------------------------------------------------------------------
SUMMARIZER_PROMPT = """\
You are a senior analyst producing the final sentiment and debate report. You \
must compress the judge's aggregate output into a polished report. Preserve \
the actual argumentative structure. Do not invent new claims.

**Topic:** {topic}

**Judge's Aggregate Analysis:**
{judge_aggregate}

Produce two outputs:

## OUTPUT 1: Structured JSON

Return valid JSON with:
{{
  "topic": "{topic}",
  "degree_of_controversy": "low | medium | high",
  "positive_positions": ["..."],
  "negative_positions": ["..."],
  "crossover_positions": ["..."],
  "antagonistic_positions": ["..."],
  "consensus_points": ["..."],
  "fringe_positions": ["..."],
  "axes_of_debate": ["..."],
  "locus_shift": "...",
  "social_cohesion": "..."
}}

## OUTPUT 2: Markdown Report

Write a markdown report with these sections (in this order):
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

Separate the JSON and markdown with the delimiter: ===MARKDOWN===

Be specific, data-driven, and concise. Every sentence should add value.
"""
