from __future__ import annotations

from .llm import ModelClient
from .models import Answer, Claim, SearchResult
from .personalization import UserProfile, profile_prompt


def answer_question(
    question: str,
    results: list[SearchResult],
    profile: UserProfile,
    client: ModelClient,
) -> Answer:
    if not results:
        text = "当前知识库没有检索到足够证据。建议上传相关资料，或在知识审查中选择联网补全公开资料。"
        return Answer(text=text, claims=[], used_results=[])

    try:
        llm_text = generate_with_llm(question, results, profile, client)
    except Exception:
        llm_text = ""
    text = llm_text or generate_fallback_answer(question, results, profile)
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
) -> str:
    if not client.enabled:
        return ""
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
                    "Cite source numbers inline."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"用户偏好:\n{profile_prompt(profile)}\n\n"
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
) -> str:
    lines = [
        f"基于当前知识库，问题“{question}”可以从以下证据回答：",
        "",
    ]
    for index, result in enumerate(results[:3], start=1):
        lines.append(f"{index}. {result.snippet}")
        lines.append(f"   来源：`{result.source_path}`")
    if profile.citation_required:
        lines.append("")
        lines.append("以上回答仅基于已入库资料；未检索到的内容不会被当作事实补充。")
    return "\n".join(lines)
