# Installing Slowave

## pip / pipx (recommended)

```bash
pip install slowave        # inside an existing venv
pipx install slowave       # isolated install, CLI available globally
```

## Homebrew

```bash
brew tap mrsalty/slowave
brew install slowave
```

## conda

```bash
conda install -c conda-forge slowave
```

*(conda-forge submission pending — check [the feedstock](https://github.com/conda-forge/slowave-feedstock) for status)*

## From source

```bash
git clone https://github.com/mrsalty/slowave
cd slowave
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
scripts/slowave-check.sh   # verify install
```

## Verify

```bash
slowave --help
slowave stats
slowave dashboard --help
```

`slowave dashboard` starts a local read-only web UI at `http://127.0.0.1:8765`
for DB/process/schema/recall inspection. Stop it with `Ctrl-C`.

## LLM backend (optional)

The default brain-only path needs no LLM. The legacy Stage 0-5 extraction path does:

```bash
# Ollama (local)
ollama pull qwen2.5:7b-instruct && ollama serve

# OpenRouter (cloud)
export OPENROUTER_API_KEY=sk-or-v1-...
```

Pass `--schema-mode llm` to any eval command to use the LLM path.
