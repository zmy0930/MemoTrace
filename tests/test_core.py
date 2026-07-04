from pathlib import Path

from tracewiki.config import Settings, ensure_dirs
from tracewiki.health_check import review_knowledge_base
from tracewiki.hybrid_retriever import HybridRetriever
from tracewiki.llm import ModelClient
from tracewiki.models import KnowledgeCard, QASession, SearchResult, SourceSpan, StagingItem, SystemLog, VectorRecord
from tracewiki.personalization import UserProfile, apply_candidate
from tracewiki.preference_distiller import create_interaction_log, distill_preferences
from tracewiki.qa import answer_question
from tracewiki.reranker import heuristic_rerank
from tracewiki.retriever import LexicalRetriever
from tracewiki.spans import build_text_spans
from tracewiki.storage import KnowledgeStore
from tracewiki.vector_index import hash_embedding
from tracewiki.web_completion import merge_staging_item
from tracewiki.wiki_agent import llm_navigation_plan, wiki_guided_results
from tracewiki.wiki_builder import build_card_from_text
from tracewiki.wiki_maintenance import (
    detect_conflicts_with_llm,
    propose_answer_capture,
    propose_page_updates_with_llm,
)
from tracewiki.wiki_organizer import enrich_card_with_links, render_index_page, render_log_page
from tracewiki.models import SourceRecord
from tracewiki.concept_normalizer import normalize_concept
from tracewiki.knowledge_graph import build_knowledge_graph


class FakeClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[str] = []

    @property
    def enabled(self) -> bool:
        return True

    def chat(self, messages, model=None):
        self.calls.append(messages[-1]["content"])
        return self.text


class FailingChatClient(FakeClient):
    def chat(self, messages, model=None):
        raise RuntimeError("model temporarily unavailable")


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        raw_dir=tmp_path / "raw",
        wiki_dir=tmp_path / "wiki",
        staging_dir=tmp_path / "staging",
        sqlite_path=tmp_path / "kb.sqlite",
        openai_base_url="",
        openai_api_key="",
        text_model="none",
        vision_model="none",
        embedding_model="none",
        vector_backend="sqlite",
        rerank_enabled=True,
    )


def test_build_card_keeps_source_path():
    source = SourceRecord(
        source_id="s1",
        path="data/raw/docs/note.md",
        filename="note.md",
        modality="text",
    )
    card = build_card_from_text(source, "# RAG 笔记\nRAG 使用检索增强生成。")
    assert "data/raw/docs/note.md" in card.content
    assert card.evidence[0]["source_path"] == "data/raw/docs/note.md"


def test_retriever_finds_relevant_card():
    card = KnowledgeCard(
        card_id="c1",
        title="RAG",
        summary="检索增强生成",
        tags=["RAG", "知识库"],
        category="concept",
        source_id="s1",
        source_path="raw/rag.md",
        content="RAG 可以让回答基于外部知识库并附带来源。",
        evidence=[{"source_path": "raw/rag.md"}],
    )
    results = LexicalRetriever([card]).search("RAG 来源")
    assert results
    assert results[0].title == "RAG"


def test_retriever_uses_source_spans_for_precise_evidence():
    source = SourceRecord(
        source_id="s1",
        path="raw/long_note.md",
        filename="long_note.md",
        modality="text",
    )
    text = "第一段介绍背景。\n\n第二段说明 SourceSpan 可以提供更细粒度证据回溯。"
    card = build_card_from_text(source, text)
    spans = build_text_spans(source, card, text)
    results = LexicalRetriever([card], spans).search("细粒度证据回溯")
    assert results
    assert results[0].span_id
    assert results[0].locator.startswith("paragraph_or_chunk")


def test_hybrid_retriever_uses_vector_records_when_lexical_misses(tmp_path):
    settings = make_settings(tmp_path)
    client = ModelClient(settings)
    card = KnowledgeCard(
        card_id="c-vector",
        title="Hidden Topic",
        summary="No literal query terms here.",
        tags=[],
        category="concept",
        source_id="s-vector",
        source_path="raw/vector.md",
        content="This card intentionally lacks the search phrase.",
        evidence=[],
    )
    span = SourceSpan(
        span_id="sp-vector",
        source_id="s-vector",
        card_id=card.card_id,
        source_path=card.source_path,
        locator="paragraph_or_chunk:1",
        text="This span is retrieved through an embedding record.",
        span_type="text",
    )
    vector = VectorRecord(
        item_id="span:sp-vector",
        item_type="span",
        text=span.text,
        vector=hash_embedding("semantic retrieval target"),
        metadata={
            "span_id": span.span_id,
            "card_id": card.card_id,
            "source_path": card.source_path,
            "locator": span.locator,
            "span_type": span.span_type,
        },
    )

    results = HybridRetriever([card], [span], [vector], client).search("semantic retrieval target", limit=1)

    assert results
    assert results[0].span_id == "sp-vector"
    assert results[0].evidence[0]["retrieval_method"] == "vector"


def test_answer_question_falls_back_when_llm_chat_fails():
    result = SearchResult(
        card_id="card-fallback",
        title="Fallback Answer",
        snippet="TraceWiki should still answer from stored evidence.",
        score=0.8,
        source_path="raw/fallback.md",
        evidence=[{"source_path": "raw/fallback.md", "locator": "paragraph_or_chunk:1"}],
    )

    answer = answer_question(
        "What happens when the model fails?",
        [result],
        UserProfile(),
        FailingChatClient(""),
    )

    assert "TraceWiki should still answer from stored evidence." in answer.text
    assert answer.claims
    assert answer.used_results == [result]


def test_store_persists_qa_sessions(tmp_path):
    settings = make_settings(tmp_path)
    store = KnowledgeStore(settings.sqlite_path, settings.wiki_dir)
    session = QASession(
        session_id="qa-1",
        question="How does TraceWiki answer?",
        answer="It answers with traceable evidence.",
        evidence=[{"source": "raw/a.md"}],
        graph_mermaid="flowchart TD\n  Q --> A",
    )

    store.add_qa_session(session)
    sessions = store.list_qa_sessions()

    assert sessions[0].session_id == "qa-1"
    assert sessions[0].evidence == [{"source": "raw/a.md"}]


def test_delete_card_removes_card_spans_vectors_and_markdown(tmp_path):
    settings = make_settings(tmp_path)
    store = KnowledgeStore(settings.sqlite_path, settings.wiki_dir)
    card = KnowledgeCard(
        card_id="card-delete",
        title="Delete Me",
        summary="Temporary card.",
        tags=["temp"],
        category="scratch",
        source_id="source-delete",
        source_path="raw/delete.md",
        content="# Delete Me",
        evidence=[],
    )
    span = SourceSpan(
        span_id="span-delete",
        source_id=card.source_id,
        card_id=card.card_id,
        source_path=card.source_path,
        locator="paragraph_or_chunk:1",
        text="temporary span",
        span_type="text",
    )
    vector = VectorRecord(
        item_id="span:span-delete",
        item_type="span",
        text=span.text,
        vector=hash_embedding(span.text),
        metadata={"span_id": span.span_id, "card_id": card.card_id},
    )

    card_path = store.upsert_card(card)
    store.replace_spans_for_card(card.card_id, [span])
    store.upsert_vectors([vector])

    assert card_path.exists()
    assert store.delete_card(card.card_id)

    assert store.list_cards() == []
    assert store.list_spans() == []
    assert store.list_vectors() == []
    assert not card_path.exists()


def test_heuristic_rerank_promotes_more_relevant_evidence():
    irrelevant = SearchResult(
        card_id="a",
        title="General notes",
        snippet="unrelated background",
        score=0.05,
        source_path="raw/a.md",
        evidence=[{"retrieval_method": "lexical"}],
    )
    relevant = SearchResult(
        card_id="b",
        title="Vector retrieval rerank",
        snippet="vector retrieval uses rerank evidence",
        score=0.0,
        source_path="raw/b.md",
        evidence=[{"retrieval_method": "hybrid"}],
    )

    reranked = heuristic_rerank("vector retrieval rerank", [irrelevant, relevant])

    assert reranked[0].card_id == "b"


def test_web_staging_merges_only_after_confirmation(tmp_path):
    settings = make_settings(tmp_path)
    ensure_dirs(settings)
    store = KnowledgeStore(settings.sqlite_path, settings.wiki_dir)
    item = StagingItem(
        staging_id="stage-1",
        title="Traceable RAG",
        url="https://example.com/rag",
        summary="A staged web page about traceable retrieval.",
        content="Traceable retrieval connects answers with source evidence.",
    )
    store.add_staging_item(item)

    assert store.list_cards() == []

    card = merge_staging_item(item.staging_id, settings, store)

    assert card.title
    assert store.list_staging_items()[0].status == "merged"
    assert store.list_cards()[0].card_id == card.card_id


def test_wiki_index_page_lists_cards_with_markdown_links(tmp_path):
    settings = make_settings(tmp_path)
    ensure_dirs(settings)
    card = KnowledgeCard(
        card_id="card-index",
        title="TraceWiki Architecture",
        summary="A wiki-based RAG architecture.",
        tags=["RAG", "Wiki"],
        category="architecture",
        source_id="source-index",
        source_path="raw/arch.md",
        content="# TraceWiki Architecture",
        evidence=[],
    )

    path = render_index_page([card], settings.wiki_dir)

    text = path.read_text(encoding="utf-8")
    assert path.name == "index.md"
    assert "[[TraceWiki_Architecture|TraceWiki Architecture]]" in text
    assert "A wiki-based RAG architecture." in text


def test_wiki_card_gets_related_wikilinks_section():
    card = KnowledgeCard(
        card_id="card-rag",
        title="RAG Pipeline",
        summary="Retrieval with evidence.",
        tags=["RAG", "Evidence"],
        category="concept",
        source_id="s1",
        source_path="raw/rag.md",
        content="# RAG Pipeline\n\nRetrieval with evidence.",
        evidence=[],
    )
    related = KnowledgeCard(
        card_id="card-evidence",
        title="Evidence Graph",
        summary="Tracks citations.",
        tags=["Evidence"],
        category="concept",
        source_id="s2",
        source_path="raw/evidence.md",
        content="# Evidence Graph",
        evidence=[],
    )

    enriched = enrich_card_with_links(card, [related])

    assert "## Wiki Links" in enriched.content
    assert "[[Evidence_Graph|Evidence Graph]]" in enriched.content


def test_llm_wikilinks_override_rule_links_when_available():
    card = KnowledgeCard(
        card_id="card-rag",
        title="RAG Pipeline",
        summary="Retrieval with evidence.",
        tags=["RAG"],
        category="concept",
        source_id="s1",
        source_path="raw/rag.md",
        content="# RAG Pipeline\n\nRetrieval with evidence.",
        evidence=[],
    )
    semantic = KnowledgeCard(
        card_id="card-source",
        title="SourceSpan Evidence",
        summary="Fine-grained traceable snippets.",
        tags=["Traceability"],
        category="evidence",
        source_id="s2",
        source_path="raw/source.md",
        content="# SourceSpan Evidence",
        evidence=[],
    )
    client = FakeClient('{"links":[{"title":"SourceSpan Evidence","reason":"semantic evidence traceability"}]}')

    enriched = enrich_card_with_links(card, [semantic], client=client)

    assert "[[SourceSpan_Evidence|SourceSpan Evidence]]" in enriched.content
    assert "semantic evidence traceability" in enriched.content


def test_llm_index_rendering_uses_model_maintained_outline(tmp_path):
    settings = make_settings(tmp_path)
    ensure_dirs(settings)
    card = KnowledgeCard(
        card_id="card-index",
        title="TraceWiki Architecture",
        summary="A wiki-based RAG architecture.",
        tags=["RAG"],
        category="architecture",
        source_id="source-index",
        source_path="raw/arch.md",
        content="# TraceWiki Architecture",
        evidence=[],
    )
    client = FakeClient("# TraceWiki Index\n\n## Important\n- [[TraceWiki_Architecture|TraceWiki Architecture]] - curated by LLM")

    path = render_index_page([card], settings.wiki_dir, client=client)

    text = path.read_text(encoding="utf-8")
    assert "curated by LLM" in text


def test_log_page_renders_system_events(tmp_path):
    settings = make_settings(tmp_path)
    ensure_dirs(settings)
    store = KnowledgeStore(settings.sqlite_path, settings.wiki_dir)
    store.add_system_log(
        SystemLog(
            log_id="log-1",
            action_type="wiki_card_created",
            summary="Created Wiki card",
            payload={"card_id": "c1"},
            created_at="2026-07-04T00:00:00+00:00",
        )
    )

    path = render_log_page(store.list_system_logs(), settings.wiki_dir)

    text = path.read_text(encoding="utf-8")
    assert path.name == "log.md"
    assert "wiki_card_created" in text
    assert "Created Wiki card" in text


def test_llm_log_page_summarizes_maintenance_events(tmp_path):
    settings = make_settings(tmp_path)
    ensure_dirs(settings)
    log = SystemLog(
        log_id="log-1",
        action_type="wiki_card_created",
        summary="Created Wiki card",
        payload={"card_id": "c1"},
        created_at="2026-07-04T00:00:00+00:00",
    )
    client = FakeClient("# TraceWiki Log\n\n## 2026-07-04\n- Updated [[RAG]] from a new source.")

    path = render_log_page([log], settings.wiki_dir, client=client)

    text = path.read_text(encoding="utf-8")
    assert "Updated [[RAG]]" in text


def test_wiki_guided_results_add_index_and_followed_page(tmp_path):
    settings = make_settings(tmp_path)
    ensure_dirs(settings)
    architecture = KnowledgeCard(
        card_id="card-arch",
        title="TraceWiki Architecture",
        summary="Links to evidence graph.",
        tags=["RAG"],
        category="architecture",
        source_id="s1",
        source_path="raw/arch.md",
        content="# TraceWiki Architecture\n\nRelated: [[Evidence_Graph|Evidence Graph]]",
        evidence=[],
    )
    evidence = KnowledgeCard(
        card_id="card-evidence",
        title="Evidence Graph",
        summary="Explains traceable citations.",
        tags=["Evidence"],
        category="concept",
        source_id="s2",
        source_path="raw/evidence.md",
        content="# Evidence Graph\n\nClaim-level citations.",
        evidence=[],
    )
    render_index_page([architecture, evidence], settings.wiki_dir)
    initial = [
        SearchResult(
            card_id=architecture.card_id,
            title=architecture.title,
            snippet=architecture.summary,
            score=0.9,
            source_path=architecture.source_path,
            evidence=[{"retrieval_method": "hybrid"}],
        )
    ]

    results = wiki_guided_results("How does evidence work?", [architecture, evidence], initial, settings.wiki_dir)

    locators = [result.locator for result in results]
    assert "wiki_index" in locators
    assert "follow_link" in locators


def test_llm_navigation_plan_selects_pages_and_followups():
    architecture = KnowledgeCard(
        card_id="card-arch",
        title="TraceWiki Architecture",
        summary="Links to evidence graph.",
        tags=["RAG"],
        category="architecture",
        source_id="s1",
        source_path="raw/arch.md",
        content="# TraceWiki Architecture",
        evidence=[],
    )
    evidence = KnowledgeCard(
        card_id="card-evidence",
        title="Evidence Graph",
        summary="Explains traceable citations.",
        tags=["Evidence"],
        category="concept",
        source_id="s2",
        source_path="raw/evidence.md",
        content="# Evidence Graph",
        evidence=[],
    )
    client = FakeClient('{"read_pages":["Evidence Graph"],"follow_links":["TraceWiki_Architecture"],"sufficient":true}')

    plan = llm_navigation_plan("How is evidence traced?", [architecture, evidence], client)

    assert plan["read_pages"] == ["Evidence Graph"]
    assert plan["follow_links"] == ["TraceWiki_Architecture"]
    assert plan["sufficient"] is True


def test_llm_page_update_conflict_and_answer_capture_proposals():
    old = KnowledgeCard(
        card_id="old",
        title="RAG",
        summary="Old summary.",
        tags=["RAG"],
        category="concept",
        source_id="s1",
        source_path="raw/old.md",
        content="# RAG\n\nOld content.",
        evidence=[],
    )
    new = KnowledgeCard(
        card_id="new",
        title="Hybrid Retrieval",
        summary="New evidence.",
        tags=["RAG"],
        category="concept",
        source_id="s2",
        source_path="raw/new.md",
        content="# Hybrid Retrieval\n\nNew content.",
        evidence=[],
    )
    update_client = FakeClient(
        '{"updates":[{"target_title":"RAG","rationale":"merge new hybrid retrieval notes","proposed_content":"# RAG\\n\\nUpdated with hybrid retrieval."}]}'
    )
    conflict_client = FakeClient(
        '{"conflicts":[{"title":"RAG definition conflict","target_title":"RAG","rationale":"definitions disagree","proposed_content":"Review old and new evidence."}]}'
    )
    capture_client = FakeClient(
        '{"capture":true,"title":"FAQ Evidence Tracing","rationale":"useful repeated question","content":"# FAQ Evidence Tracing\\n\\nAnswer summary."}'
    )

    updates = propose_page_updates_with_llm(new, [old], update_client)
    conflicts = detect_conflicts_with_llm([old, new], conflict_client)
    captures = propose_answer_capture("How trace evidence?", "Answer summary.", [old], capture_client)

    assert updates[0].proposal_type == "update_page"
    assert updates[0].target_card_id == "old"
    assert "hybrid retrieval" in updates[0].proposed_content
    assert conflicts[0].proposal_type == "conflict"
    assert captures[0].proposal_type == "answer_capture"


def test_health_check_empty_kb_reports_gap():
    issues = review_knowledge_base([])
    assert issues[0].issue_type == "coverage_gap"


def test_llm_health_review_adds_semantic_issues():
    card = KnowledgeCard(
        card_id="health-1",
        title="RAG",
        summary="Retrieval augmented generation with citations.",
        tags=["RAG"],
        category="concept",
        source_id="s1",
        source_path="raw/rag.md",
        content="# RAG\n\nRetrieval augmented generation.",
        evidence=[{"source_path": "raw/rag.md"}],
    )
    client = FakeClient(
        '{"issues":[{"title":"Missing evaluation plan","severity":"medium","issue_type":"evaluation_gap","reason":"No metrics are described","suggestion":"Add retrieval and answer quality metrics."}]}'
    )

    issues = review_knowledge_base([card], client=client)

    assert any(issue.issue_type == "evaluation_gap" for issue in issues)


def test_preference_distiller_suggests_code_examples():
    profile = UserProfile(preferred_outputs=["步骤"])
    logs = [
        create_interaction_log("怎么实现", "回答", "technical_explanation", "请给代码", "add_code", True),
        create_interaction_log("模块怎么写", "回答", "technical_explanation", "多给实现", "add_code", True),
    ]
    candidates = distill_preferences(logs, profile)
    assert any(c.field == "preferred_outputs" and c.new_value == "代码示例" for c in candidates)


def test_apply_candidate_updates_profile():
    profile = UserProfile(preferred_outputs=["步骤"])
    logs = [
        create_interaction_log("怎么实现", "回答", "technical_explanation", "请给代码", "add_code", True),
        create_interaction_log("模块怎么写", "回答", "technical_explanation", "多给实现", "add_code", True),
    ]
    candidate = distill_preferences(logs, profile)[0]
    updated = apply_candidate(profile, candidate)
    assert "代码示例" in (updated.preferred_outputs or [])
def test_concept_normalizer_merges_common_vector_database_terms():
    assert normalize_concept("向量库") == "vector-database"
    assert normalize_concept("Vector Database") == "vector-database"
    assert normalize_concept("FAISS") == "faiss"


def test_knowledge_graph_exports_cards_sources_tags_and_wikilinks():
    rag = KnowledgeCard(
        card_id="card-rag",
        title="RAG Pipeline",
        summary="Retrieval with evidence.",
        tags=["RAG", "向量库"],
        category="architecture",
        source_id="source-rag",
        source_path="raw/rag.md",
        content="# RAG Pipeline\n\nUses [[Evidence_Graph|Evidence Graph]] and vector databases.",
        evidence=[],
    )
    evidence = KnowledgeCard(
        card_id="card-evidence",
        title="Evidence Graph",
        summary="Tracks citations.",
        tags=["Evidence"],
        category="concept",
        source_id="source-evidence",
        source_path="raw/evidence.md",
        content="# Evidence Graph",
        evidence=[],
    )
    span = SourceSpan(
        span_id="span-rag",
        source_id="source-rag",
        card_id="card-rag",
        source_path="raw/rag.md",
        locator="paragraph_or_chunk:1",
        text="RAG uses retrievable source evidence.",
        span_type="text",
    )

    graph = build_knowledge_graph([rag, evidence], [span])

    node_ids = {node["id"] for node in graph["nodes"]}
    edge_keys = {(edge["source"], edge["target"], edge["type"]) for edge in graph["edges"]}

    assert "card:card-rag" in node_ids
    assert "source:source-rag" in node_ids
    assert "tag:vector-database" in node_ids
    assert ("card:card-rag", "card:card-evidence", "wikilink") in edge_keys
    assert ("card:card-rag", "source:source-rag", "source") in edge_keys
    assert graph["stats"]["cards"] == 2
    assert graph["stats"]["sources"] == 2
    assert graph["stats"]["spans"] == 1


def test_knowledge_graph_groups_related_cards_into_communities():
    rag = KnowledgeCard(
        card_id="card-rag",
        title="RAG Pipeline",
        summary="Retrieval with evidence.",
        tags=["RAG"],
        category="architecture",
        source_id="source-rag",
        source_path="raw/rag.md",
        content="# RAG Pipeline\n\nRelated: [[Evidence_Graph|Evidence Graph]]",
        evidence=[],
    )
    evidence = KnowledgeCard(
        card_id="card-evidence",
        title="Evidence Graph",
        summary="Tracks citations.",
        tags=["RAG"],
        category="concept",
        source_id="source-evidence",
        source_path="raw/evidence.md",
        content="# Evidence Graph",
        evidence=[],
    )
    unrelated = KnowledgeCard(
        card_id="card-ui",
        title="Frontend Notes",
        summary="UI implementation details.",
        tags=["React"],
        category="frontend",
        source_id="source-ui",
        source_path="raw/ui.md",
        content="# Frontend Notes",
        evidence=[],
    )

    graph = build_knowledge_graph([rag, evidence, unrelated], [])

    communities = graph["communities"]
    grouped_ids = [set(item["card_ids"]) for item in communities]
    assert {"card-rag", "card-evidence"} in grouped_ids
    assert {"card-ui"} in grouped_ids
    assert graph["stats"]["communities"] == 2
