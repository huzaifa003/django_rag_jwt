import base64, io, json, os, sys
from typing import List, Dict, Any, Optional
from openai import OpenAI
from PIL import Image
from django.conf import settings

_client_singleton: Optional[OpenAI] = None

def get_client() -> OpenAI:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = OpenAI()
    return _client_singleton

def vision_extract(image_path: str) -> Dict[str, str]:
    client = get_client()

    # Load and resize
    try:
        img = Image.open(image_path).convert('RGB')
        max_side = 1600
        w, h = img.size
        scale = min(1.0, max_side / float(max(w, h)))
        if scale < 1.0:
            img = img.resize((int(w * scale), int(h * scale)))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception as e:
        print(f'[Vision] Failed to open {image_path}: {e}', file=sys.stderr)
        return {'extracted_text': '', 'description': ''}

    prompt = (
        "Return STRICT JSON with keys exactly 'extracted_text' and 'description'. "
        "'extracted_text': all readable text as UTF-8 (tables/labels included). "
        "'description': 1-3 sentences summarizing the visible content. "
        "No extra keys or commentary."
    )

    try:
        resp = client.chat.completions.create(
            model=os.getenv('OPENAI_VISION_MODEL', settings.OPENAI_VISION_MODEL),
            messages=[
                {'role':'system','content':'You convert document page images to text + a short description.'},
                {'role':'user','content':[
                    {'type':'text','text': prompt},
                    {'type':'image_url','image_url': {'url': f'data:image/png;base64,{b64}'}},
                ]},
            ],
            
        )
        content = (resp.choices[0].message.content or '').strip().strip('`')
        if content.lower().startswith('json'):
            content = content[4:].lstrip(': \n')
        try:
            data = json.loads(content)
        except Exception:
            data = {'extracted_text': '', 'description': content}
        return {
            'extracted_text': (data.get('extracted_text') or '').strip(),
            'description': (data.get('description') or '').strip(),
        }
    except Exception as e:
        print(f'[Vision] OpenAI call failed for {image_path}: {e}', file=sys.stderr)
        return {'extracted_text': '', 'description': ''}

def synthesize_answer(question: str, hits: List[dict]) -> str:
    client = get_client()
    ctx = []
    for i, h in enumerate(hits, 1):
        body = h.get('text') or ''
        meta = f"page={h.get('page','?')} source={h.get('source','')}"
        ctx.append(f"[{i}] {meta}\n{body}")
    context = "\n\n".join(ctx) if ctx else "(no context)"
    messages = [
        {'role':'system','content':'Answer the user using only the provided context. If unsure, say you do not know. If the user just greet so greet them as well and say that i am a chatbot and i am here to help them. and if user showing his gratitude so you need to be very humble to them you should act as a proper assistant who will think and help them as a human'},
        {'role':'user','content': f"Question:\n{question}\n\nContext:\n{context}\n\nAnswer succinctly."},
    ]
    resp = client.chat.completions.create(
        model=os.getenv('OPENAI_LLM_MODEL', settings.OPENAI_LLM_MODEL),
        messages=messages,
    )
    return resp.choices[0].message.content.strip()
