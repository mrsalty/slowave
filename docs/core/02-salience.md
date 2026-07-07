# 02 — Salience Dynamics

## Overview

Salience models the brain's **memory strength** — a scalar that determines how likely a memory is to be sampled during replay, retrieved during recall, and survive decay. It is the product of three interacting forces: novelty at encoding, exponential recency decay, and recall-driven reinforcement.

## Mathematical Formulation

### State Variable

For each episodic memory \( i \):

\[
s_i(t) \in [s_{\min}, \infty), \quad s_{\min} = \text{min\_salience}
\]

### Exponential Decay

Between time \( t_0 \) and \( t \), salience decays exponentially with time constant \( \tau \):

\[
s(t) = s(t_0) \cdot e^{-(t - t_0) / \tau}
\]

\[
\tau = \text{tau\_seconds} \quad (\text{default: } 3600 \text{ s} = 1 \text{ hour})
\]

**Half-life**: \( t_{1/2} = \tau \cdot \ln(2) \approx 2495 \text{ s} \approx 41.6 \text{ min} \)

Enforced floor:

\[
s(t) = \max(s_{\min}, \; s(t))
\]

### Recall Reinforcement

Each time a memory is retrieved (and positively reinforced), salience increases additively:

\[
s \leftarrow s + \Delta_r, \quad \Delta_r = \text{recall\_reinforcement} \quad (\text{default: } 0.2)
\]

This is applied per-episode during retrieval, only to the top-k cosine-direct episodes (not graph-harvested ones).

### Consolidation Penalty

After a memory is consolidated into a prototype, its episodic salience is multiplicatively penalized:

\[
s \leftarrow \max(s_{\min}, \; s \cdot \gamma_c), \quad \gamma_c = \text{consolidation\_penalty} \quad (\text{default: } 0.5)
\]

Brain analogue: consolidated memories in cortex no longer need strong hippocampal traces.

### Proportional Sampling (for Replay)

During replay, episodes are sampled without replacement with probability proportional to salience:

\[
P(i) = \frac{s_i}{\sum_{j} s_j}
\]

Where \( s_i \) are clamped to \( \geq s_{\min} \) before normalization.

## Configuration

### `SalienceConfig`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tau_seconds` | `float` | `3600.0` | Exponential decay time constant (seconds) |
| `min_salience` | `float` | `0.01` | Absolute floor for salience |
| `novelty_weight` | `float` | `1.0` | Weight for novelty during initialization |
| `recall_reinforcement` | `float` | `0.2` | Additive boost per recall event |
| `consolidation_penalty` | `float` | `0.5` | Multiplicative penalty after consolidation |

## Computational Pipeline

```
                    ┌──────────────────┐
  encoding ────────►│ novelty_salience │──────► s₀
                    └──────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
  time passes │ decay(s, Δt)            │  s ← s · exp(-Δt/τ)
              └─────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
  on recall   │ reinforce_on_recall(s)  │  s ← s + Δᵣ
              └─────────────────────────┘
                            │
                            ▼
              ┌──────────────────────────┐
  on consol.  │ penalize_after_consol(s) │  s ← s · γ_c
              └──────────────────────────┘
```

## Key Invariants

1. Salience never drops below `min_salience` — no memory is ever fully erased.
2. Decay is purely exponential; reinforcement is purely additive — they compose sequentially.
3. Recall reinforcement is only applied to cosine-direct episodes, preventing graph-harvested self-reinforcement loops.
4. Consolidation penalty ensures the hippocampus cedes control to cortical prototypes.