def split_for_embedding(text: str, max_chars: int = 8000, overlap: int = 200):
    text = (text or '').strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks = []
    i = 0
    while i < len(text):
        j = min(i + max_chars, len(text))
        chunks.append(text[i:j])
        if j == len(text): break
        i = max(0, j - overlap)
    return chunks
