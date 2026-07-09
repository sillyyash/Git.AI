from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from core import queries

CACHE_TTL_SECONDS = 5.0
_MAX_SYMBOLS = 8
_MAX_DEFINITIONS = 12
_MAX_REFERENCES = 20
_MAX_OWNERS = 8
_MAX_COMPONENTS = 6
_MAX_RELATED_FILES = 12

_cache: Dict[str, Dict[str, Any]] = {}
_cache_timestamp: Dict[str, float] = {}

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "else",
    "for", "to", "of", "in", "on", "at", "from", "by", "with",
    "as", "is", "are", "be", "was", "were", "it", "this", "that",
    "rename", "change", "update", "remove", "add", "fix", "help",
}


def _normalize_unique(items: List[Any]) -> List[Any]:
    seen: Set[str] = set()
    normalized: List[Any] = []
    for item in items:
        if isinstance(item, (str, int, float)):
            key = str(item)
        else:
            try:
                key = json.dumps(item, sort_keys=True)
            except TypeError:
                key = repr(item)

        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def _extract_keywords(request: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", request)
    keywords = [token.lower() for token in tokens if token.lower() not in STOP_WORDS]
    return _normalize_unique(keywords)


def _build_cache_key(request: str, repository_index: Any) -> str:
    request_key = request.strip().lower()
    files = []
    if hasattr(repository_index, "files"):
        files = [getattr(f, "path", "") for f in repository_index.files]
    else:
        try:
            files = sorted(repository_index.keys())
        except Exception:
            files = []
    fingerprint = f"{len(files)}|{','.join(files)}"
    return f"{request_key}|{fingerprint}"


def _score_symbol(symbol: Dict[str, Any], keywords: List[str], query: str) -> float:
    score = 0.0
    name = symbol.get("symbol", "")
    kind = symbol.get("kind", "")
    file_path = symbol.get("file", "")
    name_lower = name.lower()
    query_lower = query.lower()

    if query_lower == name_lower:
        score += 10.0
    elif name_lower in query_lower or query_lower in name_lower:
        score += 5.0

    for keyword in keywords:
        if keyword in name_lower:
            score += 2.0
        if keyword in file_path.lower():
            score += 1.0

    if kind in {"function", "class"}:
        score += 1.0
    if kind.startswith("ref_"):
        score += 0.5

    return score


def _top_items(items: List[Any], limit: int) -> List[Any]:
    return items[:limit]


def _trim_context_if_needed(prompt_text: str, max_chars: int, context: Dict[str, Any]) -> Dict[str, Any]:
    if max_chars is None or len(prompt_text) <= max_chars:
        return context

    trimmed = context.copy()
    trimmed["definitions"] = _top_items(trimmed.get("definitions", []), 6)
    trimmed["references"] = _top_items(trimmed.get("references", []), 10)
    trimmed["related_files"] = _top_items(trimmed.get("related_files", []), 6)
    return trimmed


def build_context(
    request: str,
    repository_index: Any,
    dependency_graph: Any,
    relationship_graph: Any,
    max_tokens: int = 6000,
    max_symbols: int = _MAX_SYMBOLS,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Build a minimal repository context for a user request.

    This function only uses public query APIs from core.queries and never
    inspects repository internals directly.
    """
    cache_key = _build_cache_key(request, repository_index)
    now = time.time()
    if use_cache and cache_key in _cache and now - _cache_timestamp.get(cache_key, 0.0) < CACHE_TTL_SECONDS:
        return _cache[cache_key]

    keywords = _extract_keywords(request)
    symbol_candidates: Dict[str, Dict[str, Any]] = {}

    queries_to_run = [request] + keywords[:5]
    for query in queries_to_run:
        for symbol in queries.search_symbol(dependency_graph, relationship_graph, query, limit=20):
            key = (symbol.get("symbol"), symbol.get("kind"), symbol.get("file"))
            if key not in symbol_candidates:
                symbol_candidates[key] = {
                    "symbol": symbol.get("symbol"),
                    "kind": symbol.get("kind"),
                    "file": symbol.get("file"),
                    "score": _score_symbol(symbol, keywords, request),
                }
            else:
                symbol_candidates[key]["score"] += _score_symbol(symbol, keywords, request)

    symbols = sorted(symbol_candidates.values(), key=lambda item: item["score"], reverse=True)
    symbols = [
        {"symbol": item["symbol"], "kind": item["kind"], "file": item["file"], "score": item["score"]}
        for item in symbols
    ][:max_symbols]

    definitions: List[Dict[str, Any]] = []
    references: List[Dict[str, Any]] = []
    owners: List[str] = []
    components: List[Dict[str, Any]] = []
    related_files: List[str] = []

    for symbol in symbols:
        name = symbol.get("symbol")
        if not name:
            continue

        definitions.extend(queries.find_definitions(dependency_graph, relationship_graph, name))
        references.extend(queries.find_references(dependency_graph, relationship_graph, name))
        owners.extend(queries.find_owner(dependency_graph, relationship_graph, name))
        component = queries.find_component(dependency_graph, relationship_graph, name)
        if component:
            components.append(component)

    definitions = _normalize_unique(definitions)[:_MAX_DEFINITIONS]
    references = _normalize_unique(references)[:_MAX_REFERENCES]
    owners = _normalize_unique(owners)[:_MAX_OWNERS]
    components = _normalize_unique(components)[:_MAX_COMPONENTS]

    query_files: List[str] = []
    candidate_files = re.findall(r"[\w/\\.\-]+\.(?:py|js|jsx|tsx|html|css|json|toml|yaml|yml)", request)
    if hasattr(repository_index, "files"):
        actual_files = {f.path for f in repository_index.files}
        for candidate in candidate_files:
            if candidate in actual_files or any(path.endswith(candidate) for path in actual_files):
                query_files.append(candidate)

    seeds: List[str] = []
    if owners:
        seeds.extend(owners)
    elif query_files:
        seeds.extend(query_files)
    elif symbols:
        seeds.append(symbols[0].get("symbol") or "")

    dependency_tree = {}
    impact_analysis = {}
    if seeds:
        seed = seeds[0]
        dependency_tree = queries.dependency_tree(relationship_graph, seed)
        impact_analysis = queries.impact_analysis(relationship_graph, seed)

        for file_path in _normalize_unique(owners + query_files):
            related_files.extend(queries.find_related_files(dependency_graph, relationship_graph, file_path))

    related_files = _normalize_unique(related_files)[:_MAX_RELATED_FILES]

    summary = queries.summarize_repository(repository_index, dependency_graph, relationship_graph)
    query_history = [
        "search_symbol",
        "find_definitions",
        "find_references",
        "find_owner",
        "find_component",
        "dependency_tree",
        "impact_analysis",
        "find_related_files",
        "summarize_repository",
    ]

    context: Dict[str, Any] = {
        "request": request,
        "repository_profile": summary,
        "keywords": keywords,
        "symbols": symbols,
        "definitions": definitions,
        "references": references,
        "owners": owners,
        "components": components,
        "dependency_tree": dependency_tree,
        "impact_analysis": impact_analysis,
        "related_files": related_files,
        "query_files": _normalize_unique(query_files),
        "query_history": query_history,
        "repository_context": {
            "summary": summary,
            "symbol_count": len(symbols),
            "definition_count": len(definitions),
            "reference_count": len(references),
            "owner_count": len(owners),
            "component_count": len(components),
            "related_file_count": len(related_files),
            "estimated_context_tokens": max(0, len(json.dumps({
                "symbols": symbols,
                "definitions": definitions,
                "references": references,
                "owners": owners,
                "components": components,
                "related_files": related_files,
            }, default=str)) // 4),
        },
    }

    max_chars = int(max_tokens * 4)
    context = _trim_context_if_needed(json.dumps(context, default=str), max_chars, context)

    if use_cache:
        _cache[cache_key] = context
        _cache_timestamp[cache_key] = now

    return context
