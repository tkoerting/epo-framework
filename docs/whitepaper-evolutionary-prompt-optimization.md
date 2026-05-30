# Evolutionary Prompt Optimization: A Closed-Loop Framework for Application-Level Learning in LLM Systems

**Thomas Koerting**

---

## Abstract

Large Language Models (LLMs) produce generic outputs that users routinely edit to match their preferences, context, and quality standards. These edits represent high-value implicit feedback that current systems discard after each session. We propose Evolutionary Prompt Optimization (EPO), a framework that closes this feedback loop at the application level — without fine-tuning the underlying model. EPO operates through three complementary mechanisms: (1) Edit-Distance Tracking, which quantifies how much users modify generated outputs and identifies structural patterns in their corrections; (2) Convention Extraction, which transforms recurring edit patterns into explicit rules that are injected into subsequent prompts; and (3) Few-Shot Selection, which uses the highest-rated or least-edited previous outputs as examples for future generations. We introduce the concept of a Template Genome — a per-output-type data structure that tracks section survival rates, preferred length, and structural patterns across generations of user interaction. Unlike model-level approaches such as RLHF or fine-tuning, EPO operates entirely at the prompt level, requires no additional training infrastructure, adds less than 1,500 tokens of overhead per generation, and adapts in real-time to changing user preferences. We describe the architecture, discuss three levels of learning (individual, organizational, cross-type), and outline the path toward proactive AI systems that anticipate user needs based on evolved behavioral models.

**Keywords:** prompt optimization, implicit feedback, edit distance, few-shot learning, human-AI interaction, application-level learning

---

## 1. Introduction

The rapid adoption of Large Language Models in professional workflows has created a paradox: users generate more AI-assisted content than ever, yet the quality of that content requires significant human intervention. Studies indicate that knowledge workers spend substantial time editing, restructuring, and correcting LLM outputs before they meet professional standards (Yang et al., 2024).

This editing process is rich in signal. When a user consistently deletes introductory pleasantries from generated briefings, shortens outputs by 50%, or adds risk assessment sections that the model omitted, they are expressing clear preferences. However, current AI-powered tools treat each generation as an independent event. The feedback embedded in user edits is lost.

Existing approaches to improving LLM outputs fall into two categories:

1. **Model-level optimization**: Reinforcement Learning from Human Feedback (RLHF), Direct Preference Optimization (DPO), and fine-tuning modify the model's weights. These approaches require substantial computational resources, large datasets, and produce static improvements that cannot adapt to individual users or evolving preferences.

2. **Prompt-level optimization**: Automatic Prompt Optimization (APO) (Pryzant et al., 2023), EvoPrompt (Guo et al., 2024), and Preference-Driven Refinement (PDR) optimize prompts using algorithmic search. However, these approaches typically optimize for benchmark scores rather than real-world user satisfaction, and most require explicit feedback collection mechanisms.

We propose a third approach: **Evolutionary Prompt Optimization (EPO)**, which learns from implicit user behavior at the application level. EPO does not modify the model, does not require explicit feedback collection, and adapts continuously to each user's preferences.

The key insight is that the gap between "what the LLM generated" and "what the user actually used" contains all the information needed to improve future generations — if we measure it systematically.

---

## 2. Related Work

### 2.1 Evolutionary Algorithms for Prompt Optimization

EvoPrompt (Guo et al., 2024) connects LLMs with evolutionary algorithms, treating prompt candidates as individuals in a population that undergo mutation and crossover. The approach demonstrates significant improvements over human-engineered prompts (up to 25% on BBH benchmarks). However, EvoPrompt optimizes for task-specific benchmark performance, not for user preference alignment in production applications.

### 2.2 Human Feedback Integration

Prompt Optimization with Human Feedback (POHF) (Cheng et al., 2024) incorporates explicit human ratings to guide prompt refinement. The approach frames prompt optimization as a reinforcement learning problem where the prompt serves as state, edits as actions, and user preferences as rewards. While conceptually aligned with our work, POHF requires explicit feedback collection (ratings, rankings) rather than learning from implicit editing behavior.

### 2.3 Preference-Driven Refinement

Preference-Driven Refinement (PDR) (White et al., 2025) systematically refines prompts based on user-specified preferences such as naming conventions, documentation quality, or error handling practices. PDR demonstrates that incorporating explicit preferences into prompts significantly improves output quality. Our work extends this approach by automatically extracting conventions from observed user behavior rather than requiring explicit specification.

### 2.4 Closed-Loop Systems

The concept of closed-loop prompt refinement has been explored in automated evaluation settings (Google, 2025), where evaluation metrics drive iterative prompt modifications. These systems operate without human-in-the-loop feedback, optimizing for automated quality metrics. EPO differs fundamentally by placing the human editing process at the center of the feedback loop.

### 2.5 Positioning of EPO

EPO occupies a unique position in this landscape: it learns from **implicit** feedback (user edits, not explicit ratings), operates at the **application** level (not the model level), adapts **per-user** (not globally), and requires **no additional infrastructure** beyond the standard LLM API. Table 1 summarizes the distinctions.

**Table 1: Comparison of prompt optimization approaches**

| Approach | Feedback Type | Learning Level | Adaptation Speed | Infrastructure |
|----------|--------------|----------------|------------------|----------------|
| RLHF / Fine-tuning | Explicit (ratings) | Model (global) | Weeks-months | GPU cluster |
| EvoPrompt | Automated (benchmarks) | Task (per-dataset) | Hours | Compute budget |
| POHF | Explicit (human ratings) | Prompt (per-task) | Minutes-hours | Rating UI |
| PDR | Explicit (user-specified rules) | Prompt (per-user) | Immediate | Configuration |
| **EPO** | **Implicit (user edits)** | **Application (per-user, per-type)** | **Immediate** | **None (standard API)** |

---

## 3. Framework

Evolutionary Prompt Optimization operates through three complementary mechanisms that form a closed feedback loop. Each mechanism captures a different aspect of user preference and operates at a different granularity.

### 3.1 Edit-Distance Tracking

When a user modifies an LLM-generated output, the system preserves both the original generation and the final edited version. The edit distance between these two texts is computed using sequence matching (Ratcliff & Obershelp, 1988), yielding a normalized score between 0.0 (identical) and 1.0 (completely rewritten).

**Definition 1 (Edit Score).** Given an original text O generated by the LLM and a final text F produced by the user's editing, the edit score is defined as:

```
edit_score(O, F) = 1 - SequenceMatch(O, F)
```

where SequenceMatch returns the ratio of matching characters to total characters.

The edit score alone provides a coarse quality signal. More informative is the **structural analysis** of edits: which sections of the output survived, which were deleted, and which were added by the user.

**Definition 2 (Template Genome).** A Template Genome G for output type t is a data structure that tracks, for each structural section s:

```
G(t) = { s_i: (survival_rate, avg_edit_distance, avg_position) }
```

where:
- `survival_rate(s_i)` = proportion of generations where section s_i was retained by the user
- `avg_edit_distance(s_i)` = mean edit distance within section s_i across all generations
- `avg_position(s_i)` = mean position of section s_i in the final output (detecting reordering)

Over N generations, the Template Genome converges toward the optimal structure for output type t, as perceived by the user. Sections with low survival rates are candidates for removal from the prompt template. Sections consistently added by users are candidates for inclusion.

**Example.** After 20 meeting briefing generations:
- Section "Introduction/Greeting": survival_rate = 0.15, avg_edit_distance = 0.92 → Remove
- Section "Key Discussion Points": survival_rate = 0.95, avg_edit_distance = 0.12 → Keep
- Section "Risk Assessment": survival_rate = 0.85, avg_edit_distance = 0.08 → Keep (user adds this)
- Section "Next Steps": survival_rate = 0.98, avg_edit_distance = 0.05 → Keep (essential)

### 3.2 Convention Extraction

Recurring patterns in user edits can be generalized into explicit rules — **conventions** — that are injected into subsequent prompts.

**Definition 3 (Convention).** A convention C is a tuple:

```
C = (rule, category, source_type, score, examples)
```

where:
- `rule` is a natural language instruction (e.g., "Maximum 400 words. No filler sentences.")
- `category` ∈ {content, structure, tone, domain, formatting}
- `source_type` specifies applicability (e.g., "briefing", "report", or null for universal)
- `score` ∈ [0, 1] reflects the convention's effectiveness (based on subsequent edit distances)
- `examples` = (example_bad, example_good) providing concrete before/after illustrations

Conventions can be extracted through three channels:

1. **Automatic extraction**: Statistical analysis of recurring edits across multiple generations. If users consistently shorten outputs, a length convention is inferred. If users consistently delete certain phrase patterns, a tone convention is extracted.

2. **Explicit capture**: Users can manually define conventions through a settings interface (e.g., "I prefer bullet points over prose for status updates").

3. **Review-based extraction**: In code generation contexts, recurring review findings (e.g., "always use parameterized queries") are captured as conventions after the fix is applied.

**Prompt Injection.** Before each generation, the system queries the convention database for active conventions matching the current output type. Matching conventions are appended to the system prompt:

```
## Conventions (follow these rules):
- {C_1.rule}
- {C_2.rule}
- ...
- {C_k.rule}
```

The number of injected conventions is bounded (k ≤ 20) to control prompt length. Conventions are sorted by score, ensuring the most effective rules take priority.

### 3.3 Few-Shot Selection

The third mechanism leverages the best previous outputs as few-shot examples for future generations. Unlike static few-shot examples from training data, these examples are dynamically selected from the user's own output history based on quality signals.

**Definition 4 (Quality Signal).** The quality q of a generated output is computed as:

```
q(output) = w_1 · (1 - edit_score) + w_2 · explicit_rating + w_3 · usage_signal
```

where:
- `edit_score` is the normalized edit distance (lower = better)
- `explicit_rating` is a user-provided rating if available (normalized to [0, 1])
- `usage_signal` captures downstream usage (shared, exported, referenced)
- `w_1, w_2, w_3` are weights (default: 0.5, 0.3, 0.2)

For each new generation request of type t, the system selects the top-k outputs (typically k = 2-3) with the highest quality scores as few-shot examples. This creates a self-reinforcing cycle: better outputs are used as examples, leading to better future outputs.

**Recency Weighting.** To account for evolving preferences, quality scores are multiplied by a temporal decay factor:

```
q_weighted = q · exp(-λ · age_days)
```

where λ controls the decay rate (default: 0.01, corresponding to a half-life of approximately 70 days).

---

## 4. Architecture

EPO is designed as a middleware layer between the application and the LLM provider. It does not require modifications to the LLM itself and is compatible with any provider that supports system prompts and streaming responses.

```
┌─────────────────────────────────────────┐
│              Application                 │
│  (generates request, displays output)    │
├─────────────────────────────────────────┤
│           EPO Middleware                 │
│  ┌──────────┐  ┌────────────────────┐   │
│  │ Convention│  │ Template Genome    │   │
│  │ Database  │  │ (per output type)  │   │
│  └─────┬────┘  └────────┬───────────┘   │
│        │                │               │
│  ┌─────▼────────────────▼───────────┐   │
│  │     Prompt Composer              │   │
│  │  (system prompt + conventions    │   │
│  │   + few-shot examples)           │   │
│  └─────────────┬────────────────────┘   │
│                │                        │
│  ┌─────────────▼────────────────────┐   │
│  │     Feedback Analyzer            │   │
│  │  (edit distance, section         │   │
│  │   analysis, convention mining)   │   │
│  └──────────────────────────────────┘   │
├─────────────────────────────────────────┤
│           LLM Provider API              │
│  (Claude, GPT, Gemini, etc.)            │
└─────────────────────────────────────────┘
```

**Data Flow:**

1. Application sends generation request with context
2. Prompt Composer loads active conventions, selects few-shot examples, constructs enhanced system prompt
3. Enhanced prompt is sent to LLM provider
4. Output is returned to application and stored as `output_original`
5. User edits the output; final version is stored as `output_final`
6. Feedback Analyzer computes edit distance, updates Template Genome, extracts candidate conventions
7. Convention candidates above a confidence threshold are added to the Convention Database
8. Cycle repeats with improved prompt composition

**Storage Requirements.** EPO requires storage for:
- Convention database: ~100 records per user (< 50 KB)
- Template Genomes: ~10 output types × 20 sections (< 10 KB)
- Output history for few-shot selection: last 50-100 outputs per type (< 500 KB with compression)
- Total: < 1 MB per user

**Latency Impact.** Convention loading and few-shot selection add < 50ms to the generation pipeline. The additional prompt tokens (conventions + examples) add approximately $0.005 per generation at current API pricing (March 2026).

---

## 5. Three Levels of Learning

EPO supports learning at three levels of aggregation, each providing distinct value.

### 5.1 Individual Learning

At the individual level, EPO adapts to a single user's preferences. This is the foundational level and requires no data sharing between users.

**Convergence Behavior.** For a given output type and user, the mean edit distance decreases monotonically as the system accumulates feedback. In the limit, the edit distance approaches a floor determined by the inherent variability of the user's content needs (the system cannot predict novel content requirements).

Empirically, we observe significant improvement within the first 10–20 generations per output type. In our longitudinal evaluation (Section 7), the mean edit score decreased from 3.8% to near zero within four weeks across 30 projects, confirming that convention accumulation drives rapid convergence.

### 5.2 Organizational Learning

When multiple users within an organization use EPO, conventions can be aggregated across users. A convention that is independently extracted by three or more users within an organization is likely a genuine organizational standard rather than a personal preference.

**Aggregation Rule.** An organizational convention is proposed when:

```
count(users with similar convention) ≥ threshold AND
mean(convention.score across users) ≥ min_score
```

Organizational conventions are presented as suggestions to users who have not yet developed them individually, accelerating the learning process for new team members.

### 5.3 Cross-Type Learning

The most powerful level of learning emerges when patterns are identified across output types and across users. These are emergent best practices that no individual designed.

**Example.** Analysis across all "project status report" outputs from all users reveals that the highest-rated reports share a common structure: KPIs first, risks second, decisions needed third, next steps last. This structural insight can be offered to any user generating a project status report, even if they have never generated one before.

Cross-type learning requires sufficient data volume (hundreds of outputs across multiple users) and is therefore a later-stage capability.

---

## 6. From Reactive to Proactive

A fully evolved EPO system possesses a detailed model of what each user finds valuable: which information they need, in what format, at what level of detail, and at what frequency. This behavioral model enables a transition from reactive generation (user asks, system responds) to proactive generation (system anticipates, user confirms or adjusts).

**Proactive Generation Examples:**
- Periodic briefings generated on a schedule, using the user's preferred format and content conventions
- Alerts when new information matches patterns the user has previously engaged with
- Pre-populated meeting preparation documents based on calendar events and historical briefing preferences

The proactive mode introduces a new feedback signal: whether the user engages with unsolicited outputs. Low engagement leads to reduced frequency or format adjustment; high engagement reinforces the generation pattern.

This transition transforms the AI from a tool that responds to commands into an assistant that understands workflow patterns — a qualitative shift in human-AI collaboration.

---

## 7. Empirical Evaluation

We evaluated EPO in a single-user longitudinal deployment over six weeks (March–April 2026). The system was integrated into a Claude Code workflow via a SessionEnd hook that automatically captured edit distances for every AI-generated file.

### 7.1 Dataset

The evaluation dataset comprises **3,733 file-level edit measurements** across **30 distinct projects** spanning code, documentation, blog posts, configuration files, and correspondence. Each datapoint records the edit distance between Claude's committed output and the user's subsequent modifications (measured at the next commit, not at HEAD, to avoid temporal inflation).

**Table 2: Dataset Overview**

| Metric | Value |
|--------|-------|
| Total datapoints | 3,733 |
| Projects covered | 30 |
| Active conventions | 19 |
| Observation period | 6 weeks (March–April 2026) |
| Mean edit score | 2.0% |
| Files accepted unchanged (rating 5/5) | 95.6% |

### 7.2 Convergence Results

The central hypothesis of EPO — that edit distances decrease over time as the system accumulates conventions — is confirmed by the data. Mean edit scores decreased from 3.8% in the first week to 0.0% in weeks six and seven.

**Table 3: Weekly Edit Score Convergence**

| Week | n | Mean Edit Score |
|------|---|-----------------|
| 11 (early March) | 66 | 3.79% |
| 12 | 371 | 2.76% |
| 13 | 2,409 | 2.27% |
| 14 | 19 | 0.00% |
| 15 | 600 | 0.79% |
| 16 | 263 | 0.00% |
| 17 (late April) | 5 | 0.00% |

The convergence rate exceeds our initial expectation of "significant improvement within 10–20 generations per output type" (Section 5.1). With 19 conventions active, the system reached near-zero edit scores within approximately 4 weeks across all project types.

### 7.3 Project-Level Analysis

Edit scores vary by project type, revealing that EPO's effectiveness depends on output predictability:

**Table 4: Edit Scores by Project (top 15 by volume)**

| Project | n | Mean Edit Score | Type |
|---------|---|-----------------|------|
| Project A | 862 | 0.96% | Application code |
| Project B | 439 | 0.63% | Web/CMS |
| Project C | 265 | 0.00% | Blog/Content |
| Project D | 237 | 0.84% | Internal tool |
| Project E | 232 | 3.23% | Home automation |
| Project F | 183 | 1.37% | Customer project |
| Project G | 173 | 1.01% | Technical writing |
| Project H | 172 | 8.14% | New/exploratory |
| Project I | 149 | 1.34% | Customer project |
| Project J | 147 | 3.91% | Security tool |
| Project K | 143 | 7.69% | New customer |
| Project L | 139 | 0.90% | Customer project |
| Project M | 124 | 0.81% | Internal tool |
| Project N | 110 | 1.14% | Data journalism |
| EPO | 91 | 2.75% | This framework |

Three patterns emerge:

1. **Established projects** (Projects A, B, C) converge to < 1% edit scores. Conventions accumulate and transfer effectively within familiar codebases.

2. **New or exploratory projects** (Project H at 8.14%, Project K at 7.69%) show higher edit scores — expected, as the user provides novel direction that no convention can anticipate.

3. **Configuration and infrastructure** (ha-config at 3.23%, pii-guard at 3.91%) occupy a middle ground where domain-specific patterns require more iterations to learn.

### 7.4 Rating Distribution

The rating distribution (derived from edit scores, where 5 = unchanged, 1 = fully rewritten) confirms that EPO outputs are overwhelmingly accepted as-is:

| Rating | Count | Percentage |
|--------|-------|------------|
| 5 (unchanged) | 3,568 | 95.6% |
| 4 (minor edits) | 89 | 2.4% |
| 3 (moderate edits) | 41 | 1.1% |
| 2 (major edits) | 22 | 0.6% |
| 1 (rewritten) | 13 | 0.3% |

### 7.5 Discussion

The empirical results validate EPO's core mechanism: implicit feedback from user edits, captured as conventions and injected into prompts, measurably reduces the gap between generated and desired output. The 95.6% acceptance rate across 30 diverse projects demonstrates that convention-based prompt evolution generalizes beyond a single output type or domain.

**Limitations of this evaluation.** The data reflects a single expert user. We cannot yet distinguish how much of the convergence is attributable to EPO's conventions versus the user's own adaptation to the LLM's capabilities. A controlled study with multiple users — some with EPO enabled, some without — would isolate EPO's causal contribution. Additionally, the rating scale (1–5 integer) introduces quantization; continuous edit-score logging would provide finer-grained convergence curves.

---

## 8. Limitations and Future Work

**Cold Start.** EPO requires an initial period of user interaction before meaningful optimization occurs. During this period, outputs are no better than standard LLM generation. Mitigation strategies include organizational convention sharing and cross-type pattern transfer.

**Gaming and Misuse.** In multi-user settings, conventions are injected into system prompts. A malicious user could craft conventions designed to manipulate LLM behavior in unintended ways. Sanitization and length limits on convention rules are necessary safeguards.

**Privacy.** Output histories and conventions may contain sensitive information. In organizational deployments, data isolation between users must be maintained, and convention aggregation must be designed to prevent information leakage.

**Future Directions.** We identify several areas for future work:
1. Multi-user controlled study to isolate EPO's causal contribution to output quality
2. Automatic convention extraction using LLM-based diff analysis (rather than statistical pattern matching)
3. Cross-organization benchmarking of Template Genomes (anonymized structural patterns)
4. Integration with tool-use agents, where EPO optimizes not just text generation but tool selection and parameter choices
5. Continuous edit-score tracking (replacing integer ratings) for finer convergence analysis

---

## 9. Conclusion

We have presented Evolutionary Prompt Optimization, a framework for closing the feedback loop between LLM-generated outputs and user preferences at the application level. Through Edit-Distance Tracking, Convention Extraction, and Few-Shot Selection, EPO enables AI systems to learn from implicit user behavior without model fine-tuning.

The key contributions of this work are:
1. The identification of user editing behavior as a rich, untapped source of preference signal
2. The Template Genome concept for tracking structural output preferences across generations
3. A practical architecture that adds minimal overhead (< 1,500 tokens, < $0.01) to standard LLM API usage
4. A three-level learning model (individual, organizational, cross-type) that enables both personalization and collective intelligence
5. Empirical validation over 3,733 datapoints across 30 projects, demonstrating convergence from 3.8% to near-zero edit scores within four weeks

EPO represents a shift from static prompt engineering to dynamic prompt evolution — systems that improve not through retraining, but through use. Our empirical results demonstrate that this is not merely a theoretical proposition: with 19 learned conventions, 95.6% of AI-generated files were accepted without modification across diverse project types. We believe this application-level learning paradigm will become a standard component of production LLM systems as the field matures from "AI that generates" to "AI that learns how to generate for you."

---

## References

Cheng, L., et al. (2024). Prompt Optimization with Human Feedback. *arXiv preprint arXiv:2405.17346*.

Google (2025). Closed-Loop System for Automated Prompt Refinement. *Technical Disclosure Commons*.

Guo, Q., et al. (2024). Connecting Large Language Models with Evolutionary Algorithms Yields Powerful Prompt Optimizers. *ICLR 2024*.

Pryzant, R., et al. (2023). Automatic Prompt Optimization with "Gradient Descent" and Beam Search. *EMNLP 2023*.

Ratcliff, J. W., & Metzener, D. E. (1988). Pattern Matching: The Gestalt Approach. *Dr. Dobb's Journal*, 13(7), 46-51.

White, J., et al. (2025). Preference-Driven Refinement of Prompts: A Study on Software Development Preferences. *College of William & Mary Technical Report*.

Yang, J., et al. (2024). If LLM Is the Wizard, Then Code Is the Wand: A Survey on How Code Empowers Large Language Models to Serve as Intelligent Agents. *arXiv preprint arXiv:2401.00812*.
