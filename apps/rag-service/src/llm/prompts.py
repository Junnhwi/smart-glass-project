from __future__ import annotations

from src.retriever.hybrid import SearchHit
from src.utils.text import format_timestamp


def _stringify(value: str | None) -> str:
    return value or ""


def serialize_hit(hit: SearchHit, index: int) -> str:
    memory = hit.memory
    description = memory.caption or memory.scene_summary or ""
    lines = [
        f"hit_index: {index}",
        f"memory_id: {memory.memory_id}",
        f"captured_at: {_stringify(format_timestamp(memory.captured_at))}",
        f"location_name: {_stringify(memory.location.name)}",
        f"position_hint: {_stringify(memory.position_hint)}",
        f"description: {_stringify(description)}",
        f"matched_terms: {', '.join(hit.matched_terms)}",
    ]
    return "\n".join(lines)


def build_system_prompt() -> str:
    return (
        "You are a smart-glass memory assistant. "
        "Answer in Korean. "
        "Use only the provided memory context. "
        "Keep the answer concise, ideally one or two sentences. "
        "If the evidence is weak or missing, say you are not sure. "
        "When the question contains exclusions such as 'not', 'except', '말고', or '빼고', "
        "focus on the remaining requested object. "
        "Mention the best memory_id and one location clue if available."
    )


def build_user_prompt(*, query: str, hits: list[SearchHit]) -> str:
    if hits:
        context_block = "\n\n".join(
            serialize_hit(hit, index)
            for index, hit in enumerate(hits[:2], start=1)
        )
    else:
        context_block = "No search hits were found."

    return (
        f"Question: {query}\n\n"
        "Retrieved context:\n"
        f"{context_block}\n\n"
        "Answer using only the retrieved context."
    )
