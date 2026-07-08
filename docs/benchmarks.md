# Slowave Benchmarks

> **Alpha-stage results.** Internal runs, not independently verified. Treat as directional.
> Reproduction scripts and full run conditions: [docs/reproducibility.md](reproducibility.md)

**Scorer note.** Slowave uses keyword-overlap (is the right answer present in what was retrieved?).
Most competitors use an LLM-as-judge. Numbers are not directly comparable across scorers — each benchmark section calls this out explicitly.
All Slowave runs: **zero LLM calls**, local CPU, no API key required.

---

## At a Glance

| Benchmark | What it tests | Slowave | Best LLM-based competitor |
|---|---|---:|---|
| **LongMemEval** | Facts, updates, preferences across many sessions with realistic distractors | **87.8%** | Mem0 94.4%† |
| **LoCoMo** | Cross-session recall across real conversations, 5 categories | **78.7%** | Mem0 92.5%‡ |
| **StaleMemory** *(concrete prefs)* | Detecting when a stored preference has silently changed | **86–89%** | no published baseline |

† Mem0 uses GPT-5 as judge; Slowave uses keyword-overlap. Scores are not directly comparable across these two protocols.
‡ Mem0's LoCoMo number is self-reported and flagged by Zep as potentially reflecting a different evaluation protocol. Every independently verified competitor scores below Slowave.

**Bottom line:** Slowave delivers competitive fact recall with zero LLM calls, fully local, at $0 per query. The remaining gaps vs LLM-based systems are in implicit preference inference (−20 pp vs Mem0) and behavioral style drift (0–1%), both of which require LLM reasoning that Slowave deliberately avoids. [See known gaps →](#-known-limitations)

---

## 🧠 LongMemEval

**What it tests:** 500 questions across 6 categories — remembering facts across sessions, tracking when facts change, recalling preferences, and reasoning about time. Each question is paired with its evidence sessions (oracle split). This is the closest thing to a standard benchmark in the AI memory space and the one most competitors publish against.

| Category | n |     Slowave | Mem0¹ | Verdict |
|---|---:|------------:|---:|---|
| temporal-reasoning | 133 |   **88.0%** | 88.0% | 🟢 parity |
| single-session-user | 70 |   **95.7%** | 97.0% | 🟡 −1.3 pp |
| knowledge-update | 78 |   **94.9%** | 93.6% | 🟢 +1 pp ahead |
| single-session-assistant | 56 |   **92.9%** | 98.2% | 🟡 −5 pp |
| multi-session | 133 |   **79.7%** | 88.0% | 🔴 −8 pp |
| single-session-preference | 30 | **76.7%** | 96.7% | 🔴 −20 pp gap |
| **TOTAL** | **500** |   **87.8%** | **94.4%** | 🟡 **−6.6 pp** |

¹ Mem0: self-reported (May 2026), GPT-5 as judge. Not directly comparable to keyword-overlap scores.

**🟢 Where Slowave excels:** knowledge updates and temporal questions — competitive with or ahead of Mem0 with zero LLM calls.

**🔴 Where Slowave falls short:** multi-session recall (cross-session state tracking) and implicit preferences. The multi-session gap reflects that Slowave retrieves episodes but does not aggregate or summarise state across them. Implicit preferences require semantic inference that Slowave deliberately avoids.

> **Scorer note.** Mem0 uses GPT-5 as judge; Slowave uses keyword-overlap. The 6.6 pp gap includes both the scorer difference and genuine capability gaps. Direct comparison on the same scorer is not yet available.

---

## 💬 LoCoMo

**What it tests:** 1 986 questions across 10 real multi-session conversations, 5 categories — cross-session recall, adversarial distractors, single-session facts, temporal reasoning, and commonsense. A broad, realistic recall benchmark based on genuine human dialogues.

| Category | n | Slowave | Verdict |
|---|---:|---:|---|
| multi-session | 841 | **84.9%** | 🟢 strong cross-session recall |
| adversarial | 446 | **80.9%** | 🟡 good distractor robustness |
| single-session | 282 | **71.3%** | 🟡 ok |
| temporal | 321 | **58.9%** | 🔴 date arithmetic gap |
| commonsense | 96 | **50.0%** | 🔴 out of scope |
| **TOTAL** | **1 986** | **78.7%** | 🟢 **beats all independently verified competitors** |

> Category breakdown above is from a prior run. Individual category scores vary ±1–2 pp between runs due to consolidation non-determinism.

**🟢 Where Slowave excels:** cross-session recall — the category that matters most in real agent use. Beats LangMem (58.1%) and Zep (75.1%) with zero fine-tuning and zero LLM calls.

**🔴 Where Slowave falls short:** "How many days since X?" is arithmetic, not retrieval — Slowave doesn't have an answer-construction layer. Commonsense questions require world knowledge that was never stored. These are structural limits of any retrieval-only system.

> **On Mem0's 92.5%:** self-reported, GPT-5 judge, and flagged by Zep as potentially reflecting a different evaluation protocol. Every independently verified competitor — Zep (75.1%), LangMem (58.1%) — scores below Slowave's 78.7%.

---

## 🔄 StaleMemory

**What it tests:** Does Slowave recall the *current* preference after it silently changes — never re-stated, only implied by a shift in behavior? 1 200 scenarios across 8 coding-assistant attribute types, 3 drift patterns each. No other memory system has published results on this benchmark.

Results split sharply by whether the changed preference has a distinct keyword:

| Preference type | Examples | Detection |
|---|---|---:|
| **Concrete — distinct keyword** | programming language, naming convention, tool choice | 🟢 **86–89%** |
| Partially concrete | output format | 🟡 20% |
| Borderline | error handling | 🟡 15% |
| **Abstract — behavioral only** | communication style, explanation approach | 🔴 **0–1%** |

**🟢 Where Slowave excels:** when a preference has a distinct keyword (e.g. switching from Python to Go), Slowave reliably recalls the updated value and discards the stale one.

**🔴 Where Slowave falls short:** abstract behavioral preferences ("be more concise") are expressed through turn length and structure — there is no keyword to retrieve. Closing this gap requires an LLM to semantically compare before/after behavior. That's outside the zero-LLM design boundary.

---

## ⚠️ Known Limitations

These are the honest gaps. No sugarcoating.

- **Preference inference.** Implicit preferences score 76.7% on LME (vs 96.7% Mem0). LLM-based systems extract and verbalize preferences; Slowave can only retrieve what was *stated*. Largest capability gap vs LLM-based competitors.

- **Cross-session arithmetic.** "How many times total did I mention X?" — Slowave retrieves individual episodes but doesn't aggregate or count across them. Affects LME multi-session (−8 pp vs Mem0) and LoCoMo temporal (58.9%).

- **World knowledge.** Questions requiring knowledge never stored in memory (LoCoMo commonsense, 50.0%) are out of scope. Slowave recalls what it was told; it cannot infer what it wasn't.

- **Abstract style drift.** StaleMemory 0–1% on behavioral preferences. No keyword means no retrieval signal.

- **Not independently verified.** All numbers are from internal runs. Reproduction scripts are published — independent verification is welcome.

---

## Reproducibility

```bash
# LongMemEval full haystack (~2.3 h)
python tests/integration/longmemeval_eval.py \
  --dataset data/longmemeval/longmemeval_s_cleaned.json \
  --assignment-threshold 0.85 --top-k 10 \
  --out data/longmemeval/runs/my_lme.json

# LoCoMo (~3 min)
python tests/integration/locomo_eval.py \
  --dataset data/locomo/locomo10.json \
  --assignment-threshold 0.85 \
  --out data/locomo/runs/my_locomo.json
```

Full dataset download links, run conditions, and expected numbers: [docs/reproducibility.md](reproducibility.md)
