from __future__ import annotations
import os
from pathlib import Path
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction as ChromaOpenAIEmbeddingFunction
from django.conf import settings

class ChromaStore:
    def __init__(self, path: str | None = None, collection: str | None = None):
        self.path = Path(path or settings.CHROMA_DIR)
        self.path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.path), settings=Settings(allow_reset=True))
        self.ef = ChromaOpenAIEmbeddingFunction(
            api_key=os.getenv('OPENAI_API_KEY'),
            model_name=os.getenv('OPENAI_EMBEDDING_MODEL', settings.OPENAI_EMBEDDING_MODEL),
        )
        self.coll = self.client.get_or_create_collection(
            name=(collection or settings.CHROMA_COLLECTION),
            embedding_function=self.ef,
        )

    def upsert_chunks(self, user_id: int, document_id: int, chunks: List[dict]):
        if not chunks:
            return 0
        existing = self.coll.get()
        base = len(existing.get('ids', [])) if isinstance(existing, dict) else 0
        ids, docs, metas = [], [], []
        count = 0
        for i, ch in enumerate(chunks):
            content = (ch.get('text') or '').strip()
            if not content:
                continue
            ids.append(str(base + len(ids)))
            docs.append(content)
            md = {
                'user_id': int(user_id),
                'document_id': int(document_id),
                'page': int(ch.get('page', 0)),
                'source': str(ch.get('source', '')),
                'image_path': str(ch.get('image_path','')),
                'content_type': 'page_image',
                'chunk': int(ch.get('chunk', i))
            }
            metas.append(md)
            count += 1
        if not ids:
            return 0
        self.coll.upsert(ids=ids, documents=docs, metadatas=metas)
        return count

    # def query(self, user_id: int, text: str, top_k: int = 8) -> List[dict]:
    #     res = self.coll.query(
    #         query_texts=[text],
    #         n_results=top_k,
    #         where={'user_id': int(user_id)},
    #         include=['documents','metadatas'],
    #     )
    #     if not res or not res.get('documents'):
    #         return []
    #     out = []
    #     for doc, md in zip(res['documents'][0], res['metadatas'][0]):
    #         out.append({'text': doc, **md})
    #     return out
    
    def query(
    self,
    user_id: int,
    text: str,
    top_k: int = 8,
    document_ids: list[int] | None = None,  # new
    ) -> list[dict]:
        where = {'user_id': int(user_id)}
        if document_ids:
            # restrict to one or more of the user's own docs
            where['document_id'] = {'$in': [int(d) for d in document_ids]}

        res = self.coll.query(
            query_texts=[text],
            n_results=top_k,
            where=where,
            include=['documents','metadatas'],
        )
        out = []
        if res and res.get('documents'):
            for doc, md in zip(res['documents'][0], res['metadatas'][0]):
                out.append({'text': doc, **md})
        return out

    def delete_document(self, user_id: int, document_id: int):
        self.coll.delete(where={'$and': [{'user_id': int(user_id)}, {'document_id': int(document_id)}]})
