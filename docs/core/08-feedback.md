# 08 — Feedback System & Learning Signals

## Overview

The feedback system closes the memory loop: symbolic feedback labels from the user are converted into numeric learning signals that drive salience updates, confidence adjustments, and review flags on schemas.

## Feedback Signal

Each user feedback label maps to a `FeedbackSignal` vector with 10 components:

\[
\mathbf{\phi} = (v, c_f, e_t, e_\tau, m, o, \Delta_s, \Delta_c, r_p, r_o)
\]

| Component | Symbol | Range | Description |
|-----------|--------|-------|-------------|
| `valence` | \( v \) | [−1, +1] | Overall usefulness (dopaminergic reward) |
| `context_fit` | \( c_f \) | [−1, +1] | Match between memory and query cue |
| `truth_error` | \( e_t \) | [0, 1] | Factual wrongness (prediction error) |
| `temporal_error` | \( e_\tau \) | [0, 1] | Staleness / outdatedness |
| `missingness` | \( m \) | [0, 1] | Recall gap (needed info not retrieved) |
| `overload` | \( o \) | [0, 1] | Working memory capacity failure |
| `salience_delta` | \( \Delta_s \) | ℝ | Absolute change to schema salience |
| `confidence_delta` | \( \Delta_c \) | ℝ | Absolute change to schema confidence |
| `review_pressure` | \( r_p \) | [0, 1] | Urgency for manual review |
| `outcome_reward` | \( r_o \) | [−1, +1] | Task-level reward (separate from memory quality) |

## Feedback Label Mapping

### `useful`
\[
\mathbf{\phi}_{\text{useful}} = (1.0, 1.0, 0, 0, 0, 0, \Delta_s^{\text{use}}, \Delta_c^{\text{use}}, 0, r_o)
\]
- Schema salience: `+0.15`, confidence: `+0.05`

### `partially_useful`
\[
\mathbf{\phi}_{\text{partial}} = (0.4, 0.5, 0, 0, 0, 0, \Delta_s^{\text{part}}, 0, 0, r_o)
\]
- Schema salience: `+0.05`, confidence: 0

### `irrelevant`
\[
\mathbf{\phi}_{\text{irrel}} = (-0.4, -1.0, 0, 0, 0, 0, \Delta_s^{\text{irr}}, 0, 0, r_o)
\]
- Schema salience: `−0.10`

### `stale`
\[
\mathbf{\phi}_{\text{stale}} = (-0.6, -0.3, 0, 1.0, 0, 0, \Delta_s^{\text{stale}}, \Delta_c^{\text{stale}}, r_p^{\text{stale}}, r_o)
\]
- Schema salience: `−0.20`, confidence: `−0.15`, review pressure: `0.6`

### `wrong`
\[
\mathbf{\phi}_{\text{wrong}} = (-1.0, -0.5, 1.0, 0, 0, 0, \Delta_s^{\text{wrong}}, \Delta_c^{\text{wrong}}, r_p^{\text{wrong}}, r_o)
\]
- Schema salience: `−0.30`, confidence: `−0.30`, review pressure: `0.8`

### `missing`
\[
\mathbf{\phi}_{\text{missing}} = (-0.3, 0, 0, 0, 1.0, 0, 0, 0, 0, r_o)
\]
- No salience/confidence delta — missingness flags that something should have been retrieved but wasn't.

### `too_much_context`
\[
\mathbf{\phi}_{\text{overload}} = (-0.2, -0.2, 0, 0, 0, 1.0, 0, 0, 0, r_o)
\]
- No salience/confidence delta — overload is a gating problem, not a memory quality problem.

## Outcome Reward

The outcome label (`success`, `partial`, `unknown`, `failure`) maps independently:

| Outcome | \( r_o \) |
|---------|-----------|
| `success` | `+1.0` |
| `partial` | `+0.3` |
| `unknown` | `0.0` |
| `failure` | `−1.0` |

By default, outcome reward is **not** applied to schema reward (`apply_outcome_to_schema_reward = False`) — outcome measures task success, not memory quality.

## Schema Updates from Feedback

For each schema identified in `used_memory_ids`:

\[
s_{\text{schema}} \leftarrow s_{\text{schema}} + \Delta_s
\]

\[
c_{\text{schema}} \leftarrow c_{\text{schema}} + \Delta_c
\]

For stale/wrong schemas, `needs_review` is set when `review_pressure ≥ stale_review_threshold` or `wrong_review_threshold`.

For `irrelevant`, `stale`, `wrong` schemas, the `context_noise_score` is incremented — this feeds into the working-memory gate's noise penalty.

## Configuration

### `FeedbackConfig`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | `bool` | `True` | Master enable |
| `persist_context_snapshots` | `bool` | `True` | Store context recall events |
| `persist_response_json` | `bool` | `True` | Store response metadata |
| `persist_rendered_context` | `bool` | `False` | Store rendered text (can be large) |
| `persist_activation_trace` | `bool` | `False` | Store activation trace (very large) |
| `max_response_json_chars` | `int` | `20000` | Truncation for response JSON |
| `max_memory_content_chars` | `int` | `500` | Truncation for memory content |
| `apply_learning` | `bool` | `True` | Master learning gate |
| `apply_positive_learning` | `bool` | `True` | Enable positive reinforcement |
| `apply_negative_learning` | `bool` | `True` | Enable negative feedback |
| `apply_stale_wrong_review` | `bool` | `True` | Enable review flagging |
| `apply_outcome_to_schema_reward` | `bool` | `False` | Map outcome to schema reward |
| `context_feedback_weight` | `float` | `0.5` | Weight for context-level feedback |
| `useful_salience_delta` | `float` | `0.15` | Salience boost for `useful` |
| `useful_confidence_delta` | `float` | `0.05` | Confidence boost for `useful` |
| `partially_useful_salience_delta` | `float` | `0.05` | Salience boost for `partially_useful` |
| `irrelevant_salience_delta` | `float` | `−0.10` | Salience penalty for `irrelevant` |
| `stale_salience_delta` | `float` | `−0.20` | Salience penalty for `stale` |
| `stale_confidence_delta` | `float` | `−0.15` | Confidence penalty for `stale` |
| `stale_review_threshold` | `float` | `0.6` | Review pressure threshold for `stale` |
| `wrong_salience_delta` | `float` | `−0.30` | Salience penalty for `wrong` |
| `wrong_confidence_delta` | `float` | `−0.30` | Confidence penalty for `wrong` |
| `wrong_review_threshold` | `float` | `0.8` | Review pressure threshold for `wrong` |

## Key Invariants

1. `missing` and `too_much_context` produce no schema updates — they are retrieval/gating issues, not memory quality issues.
2. Outcome is tracked separately from memory quality — a task can succeed despite irrelevant context.
3. Salience deltas are small additive changes (`±0.05` to `±0.30`) — feedback accumulates over many sessions.
4. Review flags are irreversible until manual intervention.