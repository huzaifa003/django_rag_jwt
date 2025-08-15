# Django RAG (OpenAI Vision + Chroma, OCR-less)

This app implements your pipeline:
**Render each PDF page → OpenAI Vision (extract text + description) → chunk → OpenAI embeddings → ChromaDB**.
It also provides JWT auth, per-user file tracking, conversations with history, and a chat API that answers using retrieved chunks.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip
pip install -r requirements.txt

# Copy env
cp .env.example .env    # Windows: copy .env.example .env
# edit .env: set OPENAI_API_KEY=...

# Django init
python manage.py migrate
python manage.py createsuperuser

# Run
python manage.py runserver 0.0.0.0:8000
```

## Auth
- `POST /api/auth/register/` {username,email,password}
- `POST /api/token/` → access/refresh
- `POST /api/token/refresh/`

Use the `Authorization: Bearer <access>` header for all protected endpoints.

## Documents
- `GET /api/docs/` → list your uploads
- `POST /api/docs/` (multipart: file=<pdf>) → uploads, ingests and indexes the PDF for the current user
- `DELETE /api/docs/{id}/` → removes doc and its embeddings from Chroma

## Conversations
- `GET /api/conversations/` → list
- `POST /api/conversations/` {title?} → create
- `GET /api/conversations/{id}/` → thread with messages
- `POST /api/conversations/{id}/messages/` {message, top_k?} → RAG chat; stores user+assistant messages and attaches top sources

### How ingestion works
- Renders each page (default 200 DPI) to PNG.
- Sends page image to **OpenAI Vision (gpt-4o)** to get `{extracted_text, description}` JSON.
- Chunks the resulting text (`~1800 chars`, `200` overlap).
- Embeds with **OpenAI text-embedding-3-large** using Chroma’s built-in EF.
- Upserts into Chroma with metadata: `{user_id, document_id, page, source, image_path, chunk}` and queries with `where={"user_id": <current_user>}`.

### Resetting the vector store (dev)
Delete the folder set by `CHROMA_DIR` in `.env` to clear the index.

### Notes
- Ingestion runs inline on upload for simplicity. For large PDFs, add Celery/RQ later.
- If you previously created a Chroma collection with a different embedding function, delete the `.chroma` folder or choose a new `CHROMA_COLLECTION` name.
