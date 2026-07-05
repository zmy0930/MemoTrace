from __future__ import annotations

from .llm import ModelClient
from .memory import memory_prompt
from .models import Answer, Claim, MemoryItem, SearchResult
from .personalization import UserProfile, profile_prompt


def answer_question(
    question: str,
    results: list[SearchResult],
    profile: UserProfile,
    client: ModelClient,
    memories: list[MemoryItem] | None = None,
) -> Answer:
    memories = memories or []
    if not results:
        text = "当前知识库没有检索到足够证据。建议上传相关资料，或在知识审查中选择联网补全公开资料。"
        if prefers_concise(memories):
            text = "结论：当前知识库没有检索到足够证据。建议先上传相关资料，或从联网补全暂存区补充公开资料。"
        return Answer(text=text, claims=[], used_results=[])

    try:
        llm_text = generate_with_llm(question, results, profile, client, memories)
    except Exception:
        llm_text = ""
    text = llm_text or generate_fallback_answer(question, results, profile, memories)
    claims = [
        Claim(
            text=result.snippet,
            evidence=result.evidence,
            confidence=min(0.95, 0.55 + result.score),
        )
        for result in results[:3]
    ]
    return Answer(text=text, claims=claims, used_results=results)


def generate_with_llm(
    question: str,
    results: list[SearchResult],
    profile: UserProfile,
    client: ModelClient,
    memories: list[MemoryItem] | None = None,
) -> str:
    if not client.enabled:
        return ""
    memories = memories or []
    context = "\n\n".join(
        f"[{index}] {result.title}\n{result.snippet}\nSource: {result.source_path}"
        for index, result in enumerate(results, start=1)
    )
    return client.chat(
        [
            {
                "role": "system",
                "content": (
                    "You are TraceWiki, a source-grounded personal knowledge-base assistant. "
                    "Answer only from the provided evidence. If evidence is missing, say so. "
                    "Cite source numbers inline. User memories are style and workflow signals only; "
                    "never treat them as factual evidence."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"手动用户画像:\n{profile_prompt(profile)}\n\n"
                    f"长期记忆:\n{memory_prompt(memories)}\n\n"
                    f"问题:\n{question}\n\n"
                    f"证据:\n{context}\n\n"
                    "请用中文回答，并列出引用来源。"
                ),
            },
        ]
    )


def generate_fallback_answer(
    question: str,
    results: list[SearchResult],
    profile: UserProfile,
    memories: list[MemoryItem] | None = None,
) -> str:
    memories = memories or []
    concise = prefers_concise(memories) or profile.length_preference == "简短"
    prefer_table = has_memory(memories, ["表格", "对比"])
    result_limit = 2 if concise else 3
    intro = f"基于当前知识库，问题“{question}”可以从以下证据回答："
    lines = [f"结论：{intro}" if concise else intro, ""]

    if prefer_table:
        lines.extend(["| 证据 | 摘要 | 来源 |", "| --- | --- | --- |"])
        for index, result in enumerate(results[:result_limit], start=1):
            snippet = result.snippet.replace("|", "\\|")
            lines.append(f"| {index} | {snippet} | `{result.source_path}` |")
    else:
        for index, result in enumerate(results[:result_limit], start=1):
            lines.append(f"{index}. {result.snippet}")
            lines.append(f"   来源：`{result.source_path}`")

    if profile.citation_required:
        lines.append("")
        lines.append("以上回答仅基于已入库资料；未检索到的内容不会被当作事实补充。")
    return "\n".join(lines)


def prefers_concise(memories: list[MemoryItem]) -> bool:
    return has_memory(memories, ["简洁", "简短", "先给结论", "避免长篇"])


def has_memory(memories: list[MemoryItem], keywords: list[str]) -> bool:
    text = "\n".join(item.content for item in memories)
    return any(keyword in text for keyword in keywords)
