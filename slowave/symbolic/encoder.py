"""Text encoder: produces a dense embedding for a piece of text.

Default backend: ONNX Runtime with paraphrase-multilingual-MiniLM-L12-v2
(384-dim, 50+ languages). Swap via EncoderConfig(model_name=...).

The encoder is loaded lazily on first use so that imports stay cheap and
test runs that don't need embeddings (e.g. with synthetic vectors) don't
pay the cost of loading model weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class EncoderConfig:
    model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    normalize: bool = True
    device: str = "cpu"  # Only CPU for ONNX
    use_onnx: bool = True  # Use ONNX Runtime (recommended) vs sentence-transformers
    cache_dir: Optional[str] = None  # Custom cache directory for models


class TextEncoder:
    """Lazy wrapper around text embedding backends (ONNX or sentence-transformers).

    By default uses ONNX Runtime for CPU-optimized inference with no torch.
    If `sentence-transformers` is installed and use_onnx=False, falls back to it.
    If neither is available, `encode` raises a clear error.
    """

    def __init__(self, cfg: EncoderConfig | None = None):
        self.cfg = cfg or EncoderConfig()
        self._backend = None  # Lazy-loaded encoder instance
        self._dim: int | None = None

    def _ensure_loaded(self) -> None:
        """Initialize the encoding backend on first use."""
        if self._backend is not None:
            return

        if self.cfg.use_onnx:
            self._load_onnx_backend()
        else:
            self._load_sentence_transformers_backend()

    def _load_onnx_backend(self) -> None:
        """Load ONNX Runtime backend (recommended, no torch)."""
        try:
            from slowave.symbolic.onnx_encoder import ONNXTextEncoder

            self._backend = ONNXTextEncoder(
                model_name=self.cfg.model_name,
                cache_dir=self.cfg.cache_dir,
            )
            self._backend._ensure_loaded()
            self._dim = self._backend.dim
        except ImportError as e:
            # If ONNX libraries are missing, give a helpful error
            raise ImportError(
                "ONNX Runtime backend is configured but not installed.\n"
                "Install with: pip install onnxruntime transformers\n"
                "Or to use the legacy sentence-transformers backend:\n"
                "  EncoderConfig(use_onnx=False)\n"
                "  pip install torch sentence-transformers"
            ) from e

    def _load_sentence_transformers_backend(self) -> None:
        """Load sentence-transformers backend (legacy, requires torch).

        Only used if explicitly requested via EncoderConfig(use_onnx=False).
        """
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is required for use_onnx=False.\n"
                "Install with: pip install torch sentence-transformers\n"
                "Or use the default ONNX Runtime backend (recommended for CPU):\n"
                "  EncoderConfig(use_onnx=True)\n"
                "  pip install onnxruntime transformers"
            ) from e

        # Silence HF hub advisory warning and progress bars
        import logging as _logging
        import os as _os

        _os.environ["TQDM_DISABLE"] = "1"
        _hf_log = _logging.getLogger("huggingface_hub")
        _hf_log.setLevel(_logging.ERROR)
        for _h in _hf_log.handlers:
            _h.setLevel(_logging.ERROR)
        _logging.getLogger("huggingface_hub.utils._http").setLevel(_logging.ERROR)

        from slowave.utils.spinner import BrainSpinner

        with BrainSpinner("loading memory"):
            try:
                model = SentenceTransformer(self.cfg.model_name, device=self.cfg.device)
                self._backend = model
                try:
                    self._dim = int(model.get_embedding_dimension())
                except AttributeError:
                    self._dim = int(model.get_sentence_embedding_dimension())
            except (RuntimeError, ModuleNotFoundError, OSError) as e:
                raise RuntimeError(
                    f"sentence-transformers embedding backend failed to load.\n"
                    f"  Error: {type(e).__name__}: {e}\n"
                    f"  Likely cause: torch / torchvision / transformers version mismatch.\n"
                    f"  Fix: run: pip install --upgrade torch torchvision transformers"
                ) from e

    @property
    def dim(self) -> int:
        """Embedding dimension (384 for the default model)."""
        self._ensure_loaded()
        assert self._dim is not None
        return self._dim

    def encode(self, text: str) -> np.ndarray:
        """Embed a single string. Returns float32 [dim] (L2-normalized by default)."""
        self._ensure_loaded()
        assert self._backend is not None

        if hasattr(self._backend, "encode"):
            # ONNX backend or sentence-transformers with .encode()
            return self._backend.encode(text)
        else:
            # Fallback for any other backend
            return self._backend.encode([text])[0].astype(np.float32)

    def encode_many(self, texts: list[str]) -> np.ndarray:
        """Embed a batch. Returns float32 [N, dim]."""
        self._ensure_loaded()
        assert self._backend is not None

        if hasattr(self._backend, "encode_many"):
            # ONNX backend with explicit encode_many()
            return self._backend.encode_many(texts)
        else:
            # sentence-transformers with .encode() for batches
            vecs = self._backend.encode(
                texts,
                normalize_embeddings=self.cfg.normalize,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return vecs.astype(np.float32)
