"""Basic tests for VoiceMatch."""

import numpy as np
import pytest

from voicematch.audio import compute_similarity
from voicematch.auth import hash_password, verify_password, create_session_token, verify_session_token
from voicematch.config import EMBEDDING_DIM


class TestComputeSimilarity:
    """Tests for cosine similarity computation."""

    def test_identical_vectors(self):
        v = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        assert compute_similarity(v, v) == pytest.approx(1.0, abs=1e-5)

    def test_opposite_vectors(self):
        v = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        assert compute_similarity(v, -v) == pytest.approx(-1.0, abs=1e-5)

    def test_orthogonal_vectors(self):
        v1 = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        v2 = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        v1[0] = 1.0
        v2[1] = 1.0
        assert compute_similarity(v1, v2) == pytest.approx(0.0, abs=1e-5)

    def test_zero_vector(self):
        v = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        z = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        assert compute_similarity(v, z) == 0.0


class TestAuth:
    """Tests for authentication functions."""

    def test_hash_and_verify_password(self):
        password = "test_password_123"
        hashed = hash_password(password)
        assert verify_password(password, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct_password")
        assert not verify_password("wrong_password", hashed)

    def test_different_hashes_for_same_password(self):
        password = "same_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        # Different salts should produce different hashes
        assert hash1 != hash2
        # But both should verify
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_session_token_create_and_verify(self):
        token = create_session_token()
        assert verify_session_token(token)

    def test_invalid_session_token(self):
        assert not verify_session_token("")
        assert not verify_session_token("invalid")
        assert not verify_session_token("a:b:c")

    def test_tampered_session_token(self):
        token = create_session_token()
        # Tamper with the signature
        parts = token.split(":")
        parts[2] = "0" * len(parts[2])
        tampered = ":".join(parts)
        assert not verify_session_token(tampered)
