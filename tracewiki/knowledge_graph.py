from __future__ import annotations

from collections import Counter
from typing import Any

from .concept_normalizer import normalize_concept
from .models import KnowledgeCard, SourceSpan
from .wiki_organizer import extract_wikilink_targets, wiki_page_name


def build_knowledge_graph(cards: list[KnowledgeCard], spans: list[SourceSpan]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    card_adjacency: dict[str, set[str]] = {card.card_id: set() for card in cards}
    card_by_page = {wiki_page_name(card): card for card in cards}
    card_by_title = {card.title: card for card in cards}
    spans_by_card = Counter(span.card_id for span in spans)

    def add_node(node_id: str, label: str, node_type: str, **data: Any) -> None:
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "label": label, "type": node_type, "data": data}
        else:
            nodes[node_id]["data"].update(data)

    def add_edge(source: str, target: str, edge_type: str, label: str, weight: float = 1.0, **data: Any) -> None:
        if source == target:
            return
        key = (source, target, edge_type)
        existing = edges.get(key)
        if existing:
            existing["weight"] = round(float(existing["weight"]) + weight, 3)
            existing["data"].update(data)
            return
        edges[key] = {
            "id": f"{edge_type}:{source}->{target}",
            "source": source,
            "target": target,
            "type": edge_type,
            "label": label,
            "weight": round(weight, 3),
            "data": data,
        }

    def connect_cards(left_id: str, right_id: str) -> None:
        if left_id == right_id:
            return
        if left_id in card_adjacency and right_id in card_adjacency:
            card_adjacency[left_id].add(right_id)
            card_adjacency[right_id].add(left_id)

    cards_by_tag: dict[str, list[KnowledgeCard]] = {}
    cards_by_category: dict[str, list[KnowledgeCard]] = {}
    for card in cards:
        for tag in card.tags:
            tag_key = normalize_concept(tag)
            if tag_key:
                cards_by_tag.setdefault(tag_key, []).append(card)
        if card.category:
            cards_by_category.setdefault(normalize_concept(card.category), []).append(card)

    for grouped_cards in list(cards_by_tag.values()) + list(cards_by_category.values()):
        for index, card in enumerate(grouped_cards):
            for related in grouped_cards[index + 1 :]:
                connect_cards(card.card_id, related.card_id)

    for card in cards:
        card_node_id = f"card:{card.card_id}"
        add_node(
            card_node_id,
            card.title,
            "card",
            summary=card.summary,
            category=card.category,
            source_path=card.source_path,
            span_count=spans_by_card[card.card_id],
            page=wiki_page_name(card),
        )
        source_node_id = f"source:{card.source_id}"
        add_node(source_node_id, card.source_path, "source", source_path=card.source_path)
        add_edge(card_node_id, source_node_id, "source", "supported by source")

        if card.category:
            category_key = normalize_concept(card.category)
            category_node_id = f"category:{category_key}"
            add_node(category_node_id, card.category, "category")
            add_edge(card_node_id, category_node_id, "category", "categorized as")

        for tag in card.tags:
            tag_key = normalize_concept(tag)
            if not tag_key:
                continue
            tag_node_id = f"tag:{tag_key}"
            add_node(tag_node_id, tag, "tag", normalized=tag_key)
            add_edge(card_node_id, tag_node_id, "tag", "tagged with")

        for target in extract_wikilink_targets(card.content):
            target_card = card_by_page.get(target) or card_by_title.get(target.replace("_", " "))
            if target_card:
                add_edge(card_node_id, f"card:{target_card.card_id}", "wikilink", "links to", weight=1.5)
                connect_cards(card.card_id, target_card.card_id)

    for span in spans:
        source_node_id = f"source:{span.source_id}"
        if source_node_id in nodes and f"card:{span.card_id}" in nodes:
            add_edge(
                f"card:{span.card_id}",
                source_node_id,
                "evidence",
                "has evidence span",
                weight=0.25,
                locator=span.locator,
                span_id=span.span_id,
            )

    communities = detect_card_communities(cards, card_adjacency, spans_by_card)
    return {
        "nodes": sorted(nodes.values(), key=lambda item: (item["type"], item["label"].lower())),
        "edges": sorted(edges.values(), key=lambda item: (item["type"], item["source"], item["target"])),
        "communities": communities,
        "stats": {
            "cards": len(cards),
            "sources": len({card.source_id for card in cards}),
            "tags": len([node for node in nodes.values() if node["type"] == "tag"]),
            "categories": len([node for node in nodes.values() if node["type"] == "category"]),
            "spans": len(spans),
            "wikilinks": len([edge for edge in edges.values() if edge["type"] == "wikilink"]),
            "communities": len(communities),
        },
    }


def build_graph_view(
    graph: dict[str, Any],
    view: str = "raw",
    community_id: str | None = None,
    limit: int = 300,
) -> dict[str, Any]:
    if view == "clustered":
        visual = build_clustered_view(graph, limit=limit)
    elif view == "focus":
        visual = build_focus_view(graph, community_id=community_id, limit=limit)
    else:
        visual = build_raw_view(graph, limit=limit)
    return {
        "graph": visual,
        "stats": {
            "nodes": len(visual["nodes"]),
            "lines": len(visual["lines"]),
            "documents": int(graph.get("stats", {}).get("sources", 0)),
            "segments": int(graph.get("stats", {}).get("spans", 0)),
            "points": len([node for node in graph.get("nodes", []) if node.get("type") in {"card", "tag", "category"}]),
            "relations": len(graph.get("edges", [])),
            "evidence": int(graph.get("stats", {}).get("spans", 0)),
            "communities": len(graph.get("communities", [])),
            "rebuild_required": False,
        },
    }


def build_raw_view(graph: dict[str, Any], limit: int = 300) -> dict[str, Any]:
    source_nodes = graph.get("nodes", [])[:limit]
    visible_ids = {node["id"] for node in source_nodes}
    nodes = [visual_node(node) for node in source_nodes]
    lines = [
        visual_line(edge)
        for edge in graph.get("edges", [])
        if edge.get("source") in visible_ids and edge.get("target") in visible_ids
    ][: limit * 2]
    return {"rootId": nodes[0]["id"] if nodes else None, "nodes": nodes, "lines": lines}


def build_clustered_view(graph: dict[str, Any], limit: int = 300) -> dict[str, Any]:
    communities = graph.get("communities", [])[:limit]
    nodes = [
        {
            "id": community["id"],
            "text": community["label"],
            "type": "CommunityNode",
            "data": {
                "type": "CommunityNode",
                "community_id": community["id"],
                "summary": ", ".join(community.get("card_titles", [])[:6]),
                "content": "\n".join(community.get("card_titles", [])),
                "node_count": community.get("size", 0),
                "edge_count": community.get("span_count", 0),
                "point_ids": [f"card:{card_id}" for card_id in community.get("card_ids", [])],
                "tags": community.get("tags", []),
            },
        }
        for community in communities
    ]
    card_to_community = {
        f"card:{card_id}": community["id"]
        for community in communities
        for card_id in community.get("card_ids", [])
    }
    lines_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in graph.get("edges", []):
        source_community = card_to_community.get(edge.get("source"))
        target_community = card_to_community.get(edge.get("target"))
        if not source_community or not target_community or source_community == target_community:
            continue
        left, right = sorted([source_community, target_community])
        item = lines_by_pair.setdefault(
            (left, right),
            {"from": left, "to": right, "weight": 0.0, "relation_count": 0},
        )
        item["weight"] += float(edge.get("weight", 1.0))
        item["relation_count"] += 1
    lines = [
        {
            "id": f"community-edge:{left}->{right}",
            "from": left,
            "to": right,
            "text": f"{line['relation_count']} relations",
            "type": "community_relation",
            "data": {"type": "community_relation", **line},
        }
        for (left, right), line in lines_by_pair.items()
    ]
    return {"rootId": nodes[0]["id"] if nodes else None, "nodes": nodes, "lines": lines}


def build_focus_view(graph: dict[str, Any], community_id: str | None, limit: int = 300) -> dict[str, Any]:
    communities = graph.get("communities", [])
    community = next((item for item in communities if item.get("id") == community_id), None)
    if not community:
        return build_clustered_view(graph, limit=limit)
    card_node_ids = {f"card:{card_id}" for card_id in community.get("card_ids", [])}
    included_ids = set(card_node_ids)
    included_edges = []
    for edge in graph.get("edges", []):
        if edge.get("source") in card_node_ids or edge.get("target") in card_node_ids:
            included_edges.append(edge)
            included_ids.add(edge.get("source"))
            included_ids.add(edge.get("target"))
    nodes = [
        visual_node(node, community_id=community["id"])
        for node in graph.get("nodes", [])
        if node.get("id") in included_ids
    ][:limit]
    visible_ids = {node["id"] for node in nodes}
    lines = [
        visual_line(edge)
        for edge in included_edges
        if edge.get("source") in visible_ids and edge.get("target") in visible_ids
    ][: limit * 2]
    return {"rootId": nodes[0]["id"] if nodes else None, "nodes": nodes, "lines": lines}


def visual_node(node: dict[str, Any], community_id: str | None = None) -> dict[str, Any]:
    node_type = node.get("type", "card")
    visual_type = "KnowledgePointNode" if node_type in {"card", "tag", "category"} else "EvidenceNode"
    data = dict(node.get("data", {}))
    data.update(
        {
            "type": visual_type,
            "point_type": node_type,
            "summary": data.get("summary", node.get("label", "")),
            "content": data.get("content", data.get("summary", node.get("label", ""))),
        }
    )
    if community_id:
        data["community_id"] = community_id
    return {"id": node["id"], "text": node["label"], "type": visual_type, "data": data}


def visual_line(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": edge.get("id"),
        "from": edge.get("source"),
        "to": edge.get("target"),
        "text": edge.get("label", edge.get("type", "")),
        "type": edge.get("type"),
        "data": {
            **edge.get("data", {}),
            "type": edge.get("type"),
            "weight": edge.get("weight", 1.0),
        },
    }


def detect_card_communities(
    cards: list[KnowledgeCard],
    adjacency: dict[str, set[str]],
    spans_by_card: Counter[str],
) -> list[dict[str, Any]]:
    by_id = {card.card_id: card for card in cards}
    visited: set[str] = set()
    communities: list[dict[str, Any]] = []

    for card in sorted(cards, key=lambda item: item.title.lower()):
        if card.card_id in visited:
            continue
        stack = [card.card_id]
        component: list[str] = []
        visited.add(card.card_id)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency.get(current, set())):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)

        component_cards = [by_id[card_id] for card_id in component if card_id in by_id]
        title = community_title(component_cards)
        communities.append(
            {
                "id": "community:" + normalize_concept(title),
                "label": title,
                "card_ids": sorted(component),
                "card_titles": sorted(card.title for card in component_cards),
                "size": len(component_cards),
                "span_count": sum(spans_by_card[card.card_id] for card in component_cards),
                "tags": common_tags(component_cards),
            }
        )

    return sorted(communities, key=lambda item: (-int(item["size"]), str(item["label"]).lower()))


def community_title(cards: list[KnowledgeCard]) -> str:
    tag_counts = Counter(normalize_concept(tag) for card in cards for tag in card.tags if normalize_concept(tag))
    if tag_counts:
        return tag_counts.most_common(1)[0][0]
    category_counts = Counter(normalize_concept(card.category) for card in cards if normalize_concept(card.category))
    if category_counts:
        return category_counts.most_common(1)[0][0]
    return cards[0].title if cards else "untitled"


def common_tags(cards: list[KnowledgeCard]) -> list[str]:
    counts = Counter(normalize_concept(tag) for card in cards for tag in card.tags if normalize_concept(tag))
    return [tag for tag, _ in counts.most_common(6)]
