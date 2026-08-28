"""
jarvis/skills/rag_search/__init__.py
=====================================
Semantic Memory Search: vector-based recall across all JARVIS memories.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

log = logging.getLogger("jarvis.skills.rag_search")

_STORE = None


def _get_store():
    global _STORE
    if _STORE is None:
        from jarvis.memory.vector_store import SemanticVectorStore, VectorStoreConfig
        _STORE = SemanticVectorStore(VectorStoreConfig(persist_path="logs/vector_store.json"))
    return _STORE


def execute(
    action: str = "search",
    query: str = "",
    k: int = 5,
    category: str = "",
    content: str = "",
    doc_id: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Semantic Memory Search skill.

    Args:
        action: 'search' | 'index' | 'stats' | 'clear'
        query:  Search query for 'search' action
        k:      Max results to return
        category: Filter by category (optional)
        content: Text to index for 'index' action
        doc_id: Document ID for 'index' action
    """
    store = _get_store()
    act = action.lower().strip()

    if act == "search":
        if not query.strip():
            msg = "Vui lòng cung cấp query để tìm kiếm."
            return {"data": {"results": [], "text": msg, "success": False}, "output": msg}

        results = store.search(
            query,
            k=k,
            category_filter=category or None,
        )

        if not results:
            msg = f"Không tìm thấy ký ức nào liên quan đến: '{query}'"
            return {"data": {"results": [], "count": 0, "text": msg, "success": True}, "output": msg}

        lines = [f"🔍 Tìm thấy {len(results)} kết quả cho '{query}':"]
        for i, r in enumerate(results, 1):
            score_pct = int(r.score * 100)
            preview = r.content[:100].replace("\n", " ")
            lines.append(f"  {i}. [{r.category}] ({score_pct}%) {preview}")
        msg = "\n".join(lines)

        return {
            "data": {
                "results": [r.to_dict() for r in results],
                "count": len(results),
                "query": query,
                "text": msg,
                "success": True,
            },
            "output": msg,
        }

    elif act == "index":
        text = content or query
        if not text.strip():
            msg = "Vui lòng cung cấp content để lập chỉ mục."
            return {"data": {"text": msg, "success": False}, "output": msg}

        import time
        _doc_id = doc_id or f"manual_{int(time.time() * 1000) % 1_000_000}"
        cat = category or "manual"
        ok = store.add_document(_doc_id, text, category=cat)
        msg = f"✅ Đã lập chỉ mục văn bản (ID={_doc_id}, category={cat}): '{text[:60]}...'" if ok else "Lỗi lập chỉ mục."
        return {"data": {"text": msg, "doc_id": _doc_id, "success": ok}, "output": msg}

    elif act == "stats":
        cats = store.categories()
        size = store.size()
        msg = (
            f"📊 Vector Store Stats:\n"
            f"  • Tổng tài liệu: {size}\n"
            f"  • Danh mục: {', '.join(cats) if cats else 'trống'}"
        )
        return {"data": {"size": size, "categories": cats, "text": msg, "success": True}, "output": msg}

    elif act == "clear":
        store.clear()
        msg = "🗑️ Đã xóa toàn bộ vector index."
        return {"data": {"text": msg, "success": True}, "output": msg}

    else:
        msg = f"Hành động '{act}' không hợp lệ. Hỗ trợ: search, index, stats, clear."
        return {"data": {"text": msg, "success": False}, "output": msg}
