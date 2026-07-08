I reviewed the Slowave design documents. The architecture is conceptually ambitious: it is not just “LLM memory with embeddings”, but an attempt to model memory as a dynamical system with encoding, replay, consolidation, graph association, retrieval, decay, and feedback loops.

The strongest aspect is that Slowave separates episodic memory from semantic memory, which is much closer to cognitive neuroscience than typical RAG systems.

⸻

1. Core Slowave mathematical model

At a high level:

\textbf{Experience} \rightarrow \textbf{Episode} \rightarrow \textbf{Replay} \rightarrow \textbf{Prototype} \rightarrow \textbf{Schema} \rightarrow \textbf{Retrieval}

The system has several interacting mathematical components.

⸻

1.1 Episodic memory salience dynamics

Each memory has a state:

s_i(t) \in [s_{min}, \infty)

Salience decays:

s_i(t)=s_i(t_0)e^{-(t-t_0)/\tau}

and increases when recalled:

s_i \leftarrow s_i+\Delta_r

and decreases after consolidation:

s_i \leftarrow s_i \gamma_c

Interpretation

Slowave treats memory strength as a dynamic variable.

A memory is not:

stored forever in a vector database

but:

an object competing for survival.

This is one of the strongest conceptual choices.

⸻

Brain analogy

Very strong analogy.

Human memory shows:

* forgetting curves
* retrieval strengthening
* consolidation reducing hippocampal dependence

This resembles:

* Ebbinghaus forgetting curve
* hippocampal replay
* reconsolidation theory

The analogy:

Brain	Slowave
Memory trace strength	Salience
Forgetting	Exponential decay
Recall strengthens memory	Reinforcement
Sleep consolidation	Offline replay

⸻

Weakness

The current equation is biologically plausible but simplistic.

Human forgetting is usually modeled better by:

R(t)=\frac{1}{1+\alpha t^\beta}

(power-law forgetting)

rather than:

e^{-t/\tau}

Humans do not forget exponentially forever. Some memories become almost permanent.

A better model would probably be a multi-timescale decay:

s(t)=
a e^{-t/\tau_1}
+
b e^{-t/\tau_2}
+
c

Example:

* short-term memories: hours
* medium memories: weeks
* semantic memories: years

The brain has this hierarchy.

⸻

2. Replay and prototype formation

The replay engine is probably the most interesting component.

Sampling:

P(i)=\frac{s_i}{\sum_j s_j}

High-salience experiences are replayed more often.

Episodes are clustered into prototypes.

Prototype update:

c_{new}=
\frac{n c_{old}+e}{n+1}

This is essentially online incremental clustering.

⸻

Brain analogy

Very strong.

This maps almost directly to:

Hippocampus → Neocortex consolidation

During sleep:

1. hippocampus replays experiences
2. cortex extracts statistical regularities
3. generalized knowledge emerges

Slowave:

1. sample episodes
2. cluster embeddings
3. create semantic prototypes

The analogy:

Neuroscience	Slowave
Hippocampal replay	Replay engine
Cortical learning	Prototype formation
Memory abstraction	Schema creation

⸻

Strength

This is probably Slowave’s strongest scientific argument:

Most AI memory systems do:

conversation
 ↓
embedding
 ↓
vector database
 ↓
retrieve

Slowave does:

experience
 ↓
episodic trace
 ↓
replay
 ↓
abstraction
 ↓
semantic memory

The second is much closer to biological learning.

⸻

Weakness

The clustering assumption is still shallow.

The brain does not simply cluster similar memories.

Example:

You remember:

“I failed an exam in 2018”

and

“I failed a project deadline yesterday”

They are semantically different but share an abstract concept:

failure → learning → improvement

Human abstraction is not just centroid averaging.

A stronger formulation would include:

prototype =
f(
similarity,
causal structure,
emotional value,
prediction error,
utility
)

not only:

prototype=f(embedding)

⸻

3. Graph memory and spreading activation

Slowave builds a semantic graph.

Edges:

w_{pq}
=
\lambda_1 similarity
+
\lambda_2 transition
+
\lambda_3 coactivation

Retrieval activates nodes:

a_{t+1}(p)
=
\alpha a_t(p)
+
(1-\alpha)
\sum_q
w_{qp}a_t(q)

This is a neural-network-like diffusion process.

⸻

Brain analogy

Excellent analogy.

This resembles:

Spreading activation theory

In cognitive psychology:

A concept activates related concepts.

Example:

dog
 |
animal
 |
pet
 |
childhood

A partial cue retrieves a larger memory structure.

Slowave:

query
 ↓
prototype
 ↓
graph activation
 ↓
related memories

⸻

Strength

This solves a major weakness of vector search.

Vector databases answer:

“what is similar?”

Brains answer:

“what is related?”

Those are different.

Example:

Query:

“How did I solve my previous production outage?”

The best memory might not contain the phrase “production outage”.

It might be connected through:

Kubernetes
 ↓
incident
 ↓
rollback
 ↓
debugging strategy

Graph retrieval captures this.

⸻

Weakness

The graph is currently hand-designed.

The brain’s association network emerges from:

* coactivation
* reward
* prediction
* emotional importance

Slowave mostly uses:

* similarity
* transition
* co-occurrence

Missing:

causal edges

Example:

deploy new version
        ↓
database migration failed
        ↓
rollback required

The brain stores “because” relationships.

Slowave currently stores mostly “related-to”.

Adding causal graphs would be a major improvement.

⸻

4. Temporal memory

Slowave uses sinusoidal time embeddings:

t =
[
sin(\omega t),
cos(\omega t)
]

This creates temporal similarity.

⸻

Brain analogy

Interesting but weaker.

The brain does appear to have:

* hippocampal time cells
* sequence representations
* temporal context

The analogy:

Brain	Slowave
Time cells	Temporal embeddings
Event sequence	Timestamp encoding

⸻

Problem

The implementation treats time mostly as distance.

Humans do not remember time linearly.

Example:

A childhood memory from 20 years ago can be more accessible than yesterday’s lunch.

Human temporal importance depends on:

* emotion
* novelty
* personal identity
* repetition

A better temporal score:

T =
f(
elapsed\ time,
importance,
repetition,
context
)

⸻

5. Feedback and reinforcement

Slowave maps feedback into signals:

\phi =
(v,c_f,e_t,e_\tau,m,o,...)

This is very close to reinforcement learning.

⸻

Brain analogy

Strong.

Comparable to:

* dopamine reward signals
* prediction error
* reinforcement learning

Especially:

truth\ error

resembles:

prediction\ error

⸻

Weakness

The feedback is currently symbolic:

useful
irrelevant
stale

The brain receives continuous signals.

A stronger model:

\Delta memory =
\alpha
(
reward -
expected\ reward
)

similar to:

\delta=r+\gamma V(s')-V(s)

from reinforcement learning.

⸻

6. Supersession manifold

This is one of the more original ideas.

Instead of:

old fact
new fact
same topic

it tries to detect:

new information replaces old information

using embedding movement:

d=
\frac{new-old}{||new-old||}

and SVD direction.

⸻

Brain analogy

Partial.

Humans definitely update beliefs:

Paris is capital of France

later:

France moved capital

Old memory weakens.

This resembles:

* reconsolidation
* belief updating

⸻

Weakness

A single global replacement direction is probably too simplistic.

Different domains update differently.

Examples:

Technology:

Java 8 → Java 21

Medical:

old treatment → new treatment

Personal preference:

I like coffee → I dislike coffee

These have different semantics.

A better formulation:

direction =
f(domain, relation, context)

⸻

Overall comparison with human memory

Where Slowave matches neuroscience well

Function	Match
Episodic memory	★★★★★
Replay	★★★★★
Consolidation	★★★★★
Forgetting	★★★★
Associative retrieval	★★★★
Reinforcement	★★★★
Temporal memory	★★★
Causal reasoning	★★
Self-model / identity	★★

⸻

Biggest strengths

1. Memory as a living process

The biggest innovation is moving away from:

“database of memories”

towards:

“ecosystem of memories competing, reinforcing, merging and disappearing.”

This is much closer to biology.

⸻

2. Separation of storage and language

The idea:

LLM is a client of memory, not memory itself

is very aligned with neuroscience.

Humans do not store memories as sentences.

Language is reconstructed during recall.

⸻

3. Offline consolidation

This is probably the most differentiated part.

Most AI agents only learn online.

Slowave introduces:

experience → sleep → abstraction

which is a major missing component in current agent architectures.

⸻

Biggest weaknesses

1. Embeddings are doing too much

Currently:

meaning \approx embedding\ geometry

The brain has:

* concepts
* causes
* goals
* emotions
* motivations
* sensory grounding

Embeddings capture only one projection.

⸻

2. No active memory formation

The brain decides:

“this event matters”

before storing.

Slowave mostly uses salience after encoding.

A stronger system would have:

encoding =
f(
novelty,
surprise,
goal relevance,
emotion,
prediction error
)

⸻

3. Weak self-model

Human memory is organized around:

“things that happened to me”

Slowave has episodes but lacks a strong:

self → goals → preferences → identity

layer.

Adding an explicit self-model would make it closer to autobiographical memory.

⸻

Final assessment

Slowave is not a literal brain simulation, but the architectural analogy is unusually coherent.

The strongest biological correspondences are:

1. episodic → semantic separation
2. replay-based consolidation
3. associative graph retrieval
4. forgetting/reinforcement dynamics

The largest conceptual gaps are:

1. lack of causal memory
2. over-reliance on embedding similarity
3. limited modeling of goals/emotions/self
4. simplistic forgetting dynamics

The direction is closer to cognitive architecture research than traditional RAG. The next major evolutionary step would probably not be “better retrieval”, but adding causal, predictive, and self-referential memory structures so Slowave remembers not only what was similar, but why something mattered.