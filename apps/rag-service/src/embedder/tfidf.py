from dataclasses import dataclass
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.utils.text import tokenize_text


@dataclass(slots=True)
class TfidfIndex:
    vectorizer: TfidfVectorizer
    matrix: Any


class TfidfTextEmbedder:
    def build_index(self, texts: list[str]) -> TfidfIndex | None:
        if not texts:
            return None

        if not any(tokenize_text(text) for text in texts):
            return None

        vectorizer = TfidfVectorizer(
            tokenizer=tokenize_text,
            token_pattern=None,
            lowercase=False,
            ngram_range=(1, 2),
        )
        try:
            matrix = vectorizer.fit_transform(texts)
        except ValueError as exc:
            if "empty vocabulary" in str(exc).lower():
                return None
            raise
        return TfidfIndex(vectorizer=vectorizer, matrix=matrix)

    def score_query(self, index: TfidfIndex | None, query_text: str) -> list[float]:
        if index is None:
            return []

        query_matrix = index.vectorizer.transform([query_text])
        scores = cosine_similarity(query_matrix, index.matrix)[0]
        return [float(score) for score in scores]
