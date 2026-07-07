"""Unit tests for ONNX Runtime-based text encoder."""

import numpy as np
import pytest


class TestONNXTextEncoder:
    """Tests for ONNXTextEncoder."""

    @pytest.fixture
    def encoder(self):
        """Lazy-load encoder on first use."""
        try:
            from slowave.symbolic.onnx_encoder import ONNXTextEncoder

            return ONNXTextEncoder()
        except ImportError as e:
            pytest.skip(f"ONNX Runtime not available: {e}")

    def test_encoder_dim(self, encoder):
        """Test that encoder returns correct embedding dimension."""
        assert encoder.dim == 384, "default encoder should return 384-dim embeddings"

    def test_encode_single_text(self, encoder):
        """Test encoding a single text string."""
        text = "hello world"
        embedding = encoder.encode(text)

        # Check shape
        assert embedding.shape == (384,), f"Expected shape (384,), got {embedding.shape}"

        # Check dtype
        assert embedding.dtype == np.float32, f"Expected float32, got {embedding.dtype}"

        # Check L2 normalization (should be ~1.0)
        norm = np.linalg.norm(embedding)
        assert np.isclose(norm, 1.0, atol=1e-6), f"Expected unit norm, got {norm}"

    def test_encode_batch(self, encoder):
        """Test encoding multiple texts in batch."""
        texts = ["hello", "world", "test", "batch"]
        embeddings = encoder.encode_many(texts)

        # Check shape
        assert embeddings.shape == (4, 384), f"Expected shape (4, 384), got {embeddings.shape}"

        # Check dtype
        assert embeddings.dtype == np.float32

        # Check each row is L2 normalized
        norms = np.linalg.norm(embeddings, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-6), f"Expected unit norms, got {norms}"

    def test_encode_empty_batch(self, encoder):
        """Test encoding empty list returns empty array."""
        embeddings = encoder.encode_many([])
        assert embeddings.shape == (0, 384)

    def test_semantic_similarity(self, encoder):
        """Test that semantically similar texts have high cosine similarity."""
        text1 = "dog"
        text2 = "puppy"  # Semantically similar
        text3 = "car"  # Dissimilar

        emb1 = encoder.encode(text1)
        emb2 = encoder.encode(text2)
        emb3 = encoder.encode(text3)

        # Cosine similarity between normalized vectors is just dot product
        sim_similar = np.dot(emb1, emb2)
        sim_dissimilar = np.dot(emb1, emb3)

        # Similar should have higher similarity than dissimilar
        assert sim_similar > sim_dissimilar, (
            f"Expected similar pair ({sim_similar}) to have higher "
            f"similarity than dissimilar pair ({sim_dissimilar})"
        )

    def test_deterministic_encoding(self, encoder):
        """Test that encoding is deterministic."""
        text = "the quick brown fox jumps over the lazy dog"
        emb1 = encoder.encode(text)
        emb2 = encoder.encode(text)

        # Should be identical (or extremely close due to floating point)
        assert np.allclose(emb1, emb2, atol=1e-6), "Encoding should be deterministic"

    def test_long_text_truncation(self, encoder):
        """Test that very long texts are truncated without error."""
        # Create a text longer than max_length (512 tokens)
        long_text = " ".join(["word"] * 1000)
        embedding = encoder.encode(long_text)

        # Should still produce valid 384-dim normalized vector
        assert embedding.shape == (384,)
        assert np.isclose(np.linalg.norm(embedding), 1.0, atol=1e-6)

    def test_special_characters(self, encoder):
        """Test encoding texts with special characters."""
        texts = [
            "Hello, world!",
            "What's up?",
            "email@example.com",
            '"quoted" text',
            "café résumé naïve",  # Accented characters
        ]
        embeddings = encoder.encode_many(texts)

        # Should handle all without error
        assert embeddings.shape == (5, 384)
        assert np.all(np.isclose(np.linalg.norm(embeddings, axis=1), 1.0, atol=1e-6))
