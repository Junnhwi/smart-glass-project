from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.preprocessing import normalize

from src.utils.text import tokenize_text


DEFAULT_HASHING_VECTOR_DIMENSION = 384


@dataclass(slots=True)
class HashingVectorEmbedding:
    values: np.ndarray


class HashingTextEmbedder:
    def __init__(self, dimension: int = DEFAULT_HASHING_VECTOR_DIMENSION) -> None:
        self.dimension = dimension
        self.vectorizer = HashingVectorizer(
            tokenizer=tokenize_text,
            token_pattern=None,
            lowercase=False,
            ngram_range=(1, 2),
            alternate_sign=False,
            norm=None,
            n_features=dimension,
        )

    def embed(self, text: str | None) -> HashingVectorEmbedding | None:
        if not text:
            return None
        if not tokenize_text(text):
            return None

        matrix = self.vectorizer.transform([text])
        normalized = normalize(matrix, norm="l2")
        values = normalized.toarray()[0].astype(np.float32, copy=False)
        if not np.any(values):
            return None
        return HashingVectorEmbedding(values=values)
