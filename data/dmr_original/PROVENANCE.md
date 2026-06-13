# Original DMR candidate dataset provenance

Fetched: 2026-06-02

Source:

- Hugging Face organization: `https://huggingface.co/MemGPT`
- Dataset repo: `https://huggingface.co/datasets/MemGPT/MSC-Self-Instruct`
- Files fetched:
  - `README.md`
  - `msc_self_instruct.jsonl`

Why this is the likely original DMR dataset:

- The MemGPT paper (`arXiv:2310.08560`) states that DMR is based on the
  Multi-Session Chat (MSC) dataset and that code/data are released at
  `https://research.memgpt.ai` / `https://memgpt.ai`.
- The research page links to `https://huggingface.co/MemGPT`.
- The Hugging Face org contains `MemGPT/MSC-Self-Instruct` with exactly 500
  records, matching the Zep paper's statement that DMR comprises 500
  multi-session conversations.
- Each record has MSC dialogs plus a `self_instruct` question/answer pair.

Observed schema:

```text
500 JSONL records
keys:
  personas
  dialog
  metadata
  previous_dialogs
  init_personas
  personas_update1
  personas_update2
  self_instruct
  summary_speaker_1
  summary_speaker_2
```

Important caveat:

This fetch gives the original **data source candidate**, but reproducing the
published MemGPT/Zep DMR numbers still requires matching the original evaluation
protocol:

- ingest format and speaker perspective,
- use of current dialog vs previous dialogs,
- generated-answer step,
- LLM judge prompt,
- model used for answering/judging,
- top-k / memory retrieval settings.

The current Slowave scratch adapter only measures retrieval-context keyword
presence and is therefore not apples-to-apples with MemGPT/Zep's LLM-judged DMR.

Initial Slowave retrieval-context results:

- Harness: `tests/integration/dmr_original_eval.py`
- Scorer: keyword overlap over retrieved schemas + episodes, threshold `0.5`
- First 25 records: `23/25 = 92.0%` (partial output from a 50-record run)
- Records 25–49: `24/25 = 96.0%`
- Combined first 50 records: `47/50 = 94.0%`
- Full 500 records, chunked run: `455/500 = 91.0%`
- Full run output: `data/dmr_original/runs/slowave_dmr_original_retrieval_full_combined.json`
- Average recall latency in the full combined output: `12.47 ms`

These numbers are promising and near the published MemGPT/Zep DMR range, but
they are still retrieval-context scores, not generated-answer / LLM-judge scores.
