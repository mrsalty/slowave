"""`python -m slowave` dispatches to the Click CLI."""
import os

# macOS note: FAISS + PyTorch can sometimes load multiple OpenMP runtimes.
# Pragmatic workaround to avoid a hard crash.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from slowave.cli.main import main

if __name__ == "__main__":
    main()
