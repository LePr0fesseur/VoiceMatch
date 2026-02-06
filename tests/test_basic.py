"""Basic tests for VoiceMatch."""

import numpy as np
import pytest

from voicematch.youtube import parse_actor_from_title
from voicematch.audio import compute_similarity
from voicematch.config import EMBEDDING_DIM


class TestParseActorFromTitle:
    """Tests for YouTube title parsing."""

    def test_voix_francaise_de_pattern(self):
        info = parse_actor_from_title(
            "La voix française de Jim Carrey - Emmanuel Curtil"
        )
        assert info["original_actor"] == "Jim Carrey"
        assert info["dubber"] == "Emmanuel Curtil"

    def test_doubleur_de_pattern(self):
        info = parse_actor_from_title(
            "Doubleur de Tom Hanks - Jean-Philippe Puymartin"
        )
        assert info["original_actor"] == "Tom Hanks"
        assert info["dubber"] == "Jean-Philippe Puymartin"

    def test_double_pattern(self):
        info = parse_actor_from_title("Emmanuel Curtil double Jim Carrey")
        assert info["dubber"] == "Emmanuel Curtil"
        assert info["original_actor"] == "Jim Carrey"

    def test_dash_separator(self):
        info = parse_actor_from_title(
            "Patrick Poivey - doubleur de Bruce Willis"
        )
        assert info["dubber"] == "Patrick Poivey"
        assert "Bruce Willis" in info["original_actor"]

    def test_raw_title_always_present(self):
        title = "Some random title"
        info = parse_actor_from_title(title)
        assert info["raw_title"] == title


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
