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

def synthesize_answer(question: str, hits: List[dict], conversation_history: List[dict] = None) -> str:
    client = get_client()
    
    # Build conversation context from history
    conversation_messages = []
    if conversation_history:
        # Add conversation history (limit to last 10 messages to avoid token limits)
        for msg in conversation_history[-10:]:
            conversation_messages.append({
                'role': msg['role'],
                'content': msg['content']
            })
    
    # Check if this is a generic conversation (no hits provided)
    if not hits:
        # For generic conversations, use a more conversational system prompt
        system_content = (
            "You are a helpful AI assistant. Respond naturally to greetings, gratitude, and casual conversation. "
            "Be warm, friendly, and acknowledge the user appropriately. Keep responses concise but engaging. "
            "Maintain context from the conversation history and refer to previous messages when relevant. "
            "If the user asks follow-up questions or refers to previous topics, use the conversation history to provide contextual responses."
        )
        
        system_message = {
            'role': 'system',
            'content': system_content
        }
        
        messages = [system_message] + conversation_messages + [{'role': 'user', 'content': question}]
    else:
        # For document-related queries, use RAG context
        ctx = []
        for i, h in enumerate(hits, 1):
            body = h.get('text') or ''
            meta = f"page={h.get('page','?')} source={h.get('source','')}"
            ctx.append(f"[{i}] {meta}\n{body}")
        context = "\n\n".join(ctx) if ctx else "(no context)"
        
        system_content = (
            "Answer the user using the provided context and conversation history. If unsure, say you do not know. "
            "If the user just greet so greet them as well and say that i am a chatbot and i am here to help them. "
            "and if user showing his gratitude so you need to be very humble to them you should act as a proper assistant who will think and help them as a human. "
            "If the user ask very generic questions so you should sounds like that you acknowledge them and say that you are here to help them and you will think and help them as a human and understand the context of the chat properly and answer according to it. "
            "For Greetings and simple conversation and gratitude you shouldnt have to return me the sources from the chromadb context. "
            "Maintain conversation context and refer to previous messages when relevant. "
            "If the user asks follow-up questions about previously discussed topics, use both the conversation history and the provided context to give comprehensive answers."
        )
        
        system_message = {
            'role': 'system',
            'content': system_content
        }
        
        # Combine conversation history with current question and context
        current_question = f"Question:\n{question}\n\nContext:\n{context}\n\nAnswer succinctly."
        
        messages = [system_message] + conversation_messages + [{'role': 'user', 'content': current_question}]
    
    resp = client.chat.completions.create(
        model=os.getenv('OPENAI_LLM_MODEL', settings.OPENAI_LLM_MODEL),
        messages=messages,
    )
    return resp.choices[0].message.content.strip()
