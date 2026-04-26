from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
)


logger = logging.getLogger(__name__)


@dataclass
class AzureSearchSettings:
    """Configuration for Azure AI Search integration."""

    endpoint: str = ""
    api_key: str = ""
    index_name: str = ""

    @property
    def is_configured(self) -> bool:
        """Check if Azure Search is properly configured."""
        return bool(self.endpoint and self.index_name)

    @classmethod
    def from_environment(cls) -> AzureSearchSettings:
        """Load settings from environment variables."""
        endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "").strip()
        api_key = os.getenv("AZURE_SEARCH_API_KEY", "").strip()
        index_name = os.getenv("AZURE_SEARCH_INDEX_NAME", "mykb-notes").strip()
        return cls(endpoint=endpoint, api_key=api_key, index_name=index_name)


class AzureSearchIndexManager:
    """Manages Azure AI Search index creation and document indexing."""

    def __init__(self, settings: AzureSearchSettings) -> None:
        self.settings = settings
        self.index_name = settings.index_name
        self._index_client: SearchIndexClient | None = None
        self._search_client: SearchClient | None = None

        if not settings.is_configured:
            logger.warning("Azure Search not configured - search features will use local fallback")
            return

        try:
            self._index_client = self._create_index_client()
            self._ensure_index_exists()
        except Exception as e:
            logger.warning(f"Failed to initialize Azure Search: {e}")
            self._index_client = None

    def _create_index_client(self) -> SearchIndexClient:
        """Create and return a SearchIndexClient with proper authentication."""
        if self.settings.api_key:
            credential = AzureKeyCredential(self.settings.api_key)
            return SearchIndexClient(endpoint=self.settings.endpoint, credential=credential)

        credential = DefaultAzureCredential()
        return SearchIndexClient(endpoint=self.settings.endpoint, credential=credential)

    def _get_search_client(self) -> SearchClient | None:
        """Get or create a SearchClient instance."""
        if self._search_client is None and self._index_client is not None:
            if self.settings.api_key:
                credential = AzureKeyCredential(self.settings.api_key)
                self._search_client = SearchClient(
                    endpoint=self.settings.endpoint,
                    index_name=self.index_name,
                    credential=credential,
                )
            else:
                credential = DefaultAzureCredential()
                self._search_client = SearchClient(
                    endpoint=self.settings.endpoint,
                    index_name=self.index_name,
                    credential=credential,
                )
        return self._search_client

    def _ensure_index_exists(self) -> None:
        """Create the search index if it doesn't already exist."""
        if not self._index_client:
            return

        try:
            self._index_client.get_index(self.index_name)
            logger.info(f"Index '{self.index_name}' already exists")
        except ResourceNotFoundError:
            logger.info(f"Creating index '{self.index_name}'")
            index = self._build_index()
            self._index_client.create_index(index)

    def _build_index(self) -> SearchIndex:
        """Build the search index schema."""
        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchField(
                name="title",
                type=SearchFieldDataType.String,
                searchable=True,
                analyzer_name="en.microsoft",
            ),
            SearchField(
                name="content",
                type=SearchFieldDataType.String,
                searchable=True,
                analyzer_name="en.microsoft",
            ),
            SearchField(
                name="relative_path",
                type=SearchFieldDataType.String,
                searchable=True,
                analyzer_name="en.microsoft",
            ),
            SearchField(
                name="snippet",
                type=SearchFieldDataType.String,
                searchable=False,
            ),
            SimpleField(name="score", type=SearchFieldDataType.Double),
        ]

        return SearchIndex(name=self.index_name, fields=fields)

    def index_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        relative_path: str,
        snippet: str = "",
        score: float = 1.0,
    ) -> bool:
        """Index a single document to Azure Search."""
        if not self._get_search_client():
            return False

        try:
            document = {
                "id": doc_id,
                "title": title,
                "content": content,
                "relative_path": relative_path,
                "snippet": snippet,
                "score": score,
            }
            self._search_client.upload_documents(documents=[document])
            return True
        except Exception as e:
            logger.warning(f"Failed to index document {doc_id}: {e}")
            return False

    def index_documents(self, documents: list[dict]) -> bool:
        """Index multiple documents to Azure Search."""
        if not self._get_search_client():
            return False

        try:
            logger.debug(f"Uploading {len(documents)} documents to index {self.index_name}")
            result = self._search_client.upload_documents(documents=documents)
            logger.debug(f"Upload result: {result}")
            return True
        except Exception as e:
            logger.error(f"Failed to index {len(documents)} documents: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def search(self, query: str, top: int = 10) -> list[dict] | None:
        """Search the index using hybrid (keyword + semantic) search."""
        client = self._get_search_client()
        if not client:
            return None

        try:
            results = client.search(
                search_text=query,
                top=top,
                include_total_count=True,
            )
            return list(results)
        except Exception as e:
            logger.warning(f"Search failed: {e}")
            return None

    def is_available(self) -> bool:
        """Check if Azure Search is available and configured."""
        return self._get_search_client() is not None
