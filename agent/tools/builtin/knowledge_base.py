from __future__ import annotations

from typing import Any

from ..base import BaseTool, ToolExecutionError, ToolSchema


class KnowledgeSearchTool(BaseTool):
    name = "knowledge_search"
    description = (
        "Search the user's personal MongoDB-backed knowledge base. Use this when the user asks "
        "about uploaded files, indexed web pages, saved chat records, personal documents, or asks "
        "to answer with citations from their document library."
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The question or keywords to search in the knowledge base.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 6,
                        "description": "Maximum number of matching chunks to return.",
                    },
                },
                "required": ["query"],
            },
        )

    async def execute(
        self,
        query: str,
        limit: int = 6,
        current_user_id: int | None = None,
        **_: Any,
    ) -> str:
        if current_user_id is None:
            raise ToolExecutionError(self.name, "Missing current user id")
        from backend.knowledge_service import format_search_results, search_knowledge

        results = await search_knowledge(int(current_user_id), query, limit=limit)
        return format_search_results(results)


class KnowledgeListDocumentsTool(BaseTool):
    name = "knowledge_list_documents"
    description = "List documents currently indexed in the user's personal knowledge base."

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    async def execute(self, current_user_id: int | None = None, **_: Any) -> str:
        if current_user_id is None:
            raise ToolExecutionError(self.name, "Missing current user id")
        from backend.knowledge_service import list_documents

        docs = await list_documents(int(current_user_id))
        if not docs:
            return "The knowledge base is empty."
        lines = ["Indexed knowledge documents:"]
        for doc in docs[:100]:
            lines.append(
                f"- {doc['title']} ({doc.get('source_type')}, {doc.get('chunk_count', 0)} chunks, id={doc['id']})"
            )
        return "\n".join(lines)
