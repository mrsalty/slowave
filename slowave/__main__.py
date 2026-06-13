"""`python -m slowave` dispatches to the Click CLI."""
import os

# macOS note: FAISS + ONNX Runtime can sometimes load multiple OpenMP runtimes.
# Pragmatic workaround to avoid a hard crash.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")

import logging as _logging
_logging.getLogger("huggingface_hub").setLevel(_logging.ERROR)
_logging.getLogger("onnxruntime").setLevel(_logging.ERROR)

from slowave.cli.main import main

if __name__ == "__main__":
    main()
