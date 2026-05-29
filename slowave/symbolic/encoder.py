"""Text encoder: produces a dense embedding for a piece of text.

Default backend: sentence-transformers `bge-small-en-v1.5` (384-dim).

The encoder is loaded lazily on first use so that imports stay cheap and
test runs that don't need embeddings (e.g. with synthetic vectors) don't
pay the cost of loading model weights.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class EncoderConfig:
    model_name: str = "BAAI/bge-small-en-v1.5"
    normalize: bool = True
    device: str = "cpu"


class TextEncoder:
    """Lazy wrapper around sentence-transformers.

    If `sentence-transformers` is not installed (e.g. for the latent-only
    synthetic demo), `encode` raises a clear error so the user can install
    it. The rest of the system stays usable without it.
    """

    def __init__(self, cfg: EncoderConfig | None = None):
        self.cfg = cfg or EncoderConfig()
        self._model = None
        self._dim: int | None = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is required for text encoding. "
                "Install it with: pip install sentence-transformers"
            ) from e
        # Silence HF hub advisory warning and progress bars.
        # Must run after the import because sentence_transformers imports
        # huggingface_hub which resets the logger level to WARNING.
        import logging as _logging
        _logging.getLogger("huggingface_hub").setLevel(_logging.ERROR)
        _logging.getLogger("huggingface_hub.utils._http").setLevel(_logging.ERROR)
        try:
            self._model = SentenceTransformer(self.cfg.model_name, device=self.cfg.device)
        except (RuntimeError, ModuleNotFoundError, OSError) as e:
            raise RuntimeError(
                f"Local embedding backend failed to load.\n"
                f"  Error: {type(e).__name__}: {e}\n"
                f"  Likely cause: torch / torchvision / transformers version mismatch.\n"
                f"  Tested Python versions: 3.10\u20133.12. Python 3.13 is not yet supported.\n"
                f"  Fix: use Python 3.10\u20133.12, or run: pip install --upgrade torch torchvision transformers"
            ) from e
        # Use the current API name; fall back to the deprecated one for older versions
        try:
            self._dim = int(self._model.get_embedding_dimension())
        except AttributeError:
            self._dim = int(self._model.get_sentence_embedding_dimension())

    @property
    def dim(self) -> int:
        self._ensure_loaded()
        assert self._dim is not None
        return self._dim

    def encode(self, text: str) -> np.ndarray:
        """Embed a single string. Returns float32 [dim] (L2-normalized by default)."""
        self._ensure_loaded()
        assert self._model is not None
        vec = self._model.encode(
            [text],
            normalize_embeddings=self.cfg.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vec[0].astype(np.float32)

    def encode_many(self, texts: list[str]) -> np.ndarray:
        """Embed a batch. Returns float32 [N, dim]."""
        self._ensure_loaded()
        assert self._model is not None
        vecs = self._model.encode(
            texts,
            normalize_embeddings=self.cfg.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vecs.astype(np.float32)
