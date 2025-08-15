import os
from django.conf import settings
from django.contrib.auth.models import User
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Document, Conversation, Message, MessageSource
from .serializers import RegisterSerializer, DocumentSerializer, ConversationSerializer, MessageSerializer
from .extract import extract_pdf_pages_as_images
from .openai_helpers import vision_extract, synthesize_answer
from .textutils import split_for_embedding
from .store import ChromaStore

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

class DocumentListCreateView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request):
        docs = Document.objects.filter(owner=request.user).order_by('-created_at')
        return Response(DocumentSerializer(docs, many=True).data)

    def post(self, request):
        if 'file' not in request.data:
            return Response({'detail':'No file uploaded'}, status=400)
        f = request.data['file']
        doc = Document.objects.create(
            owner=request.user,
            file=f,
            original_name=getattr(f, 'name', 'uploaded.pdf'),
        )
        # Ingest: render pages -> vision -> chunk -> chroma
        store = ChromaStore()
        abs_path = doc.file.path
        records = extract_pdf_pages_as_images(abs_path, out_dir=settings.MEDIA_ROOT, dpi=200, max_pages=None)
        chunks = []
        for rec in records:
            info = vision_extract(rec['image_path'])
            print(info)
            text = (info.get('extracted_text') or '').strip()
            desc = (info.get('description') or '').strip()
            content = text if text else desc
            for idx, chunk in enumerate(split_for_embedding(content)):
                chunks.append({
                    'text': chunk,
                    'page': rec['page'],
                    'source': rec['source'],
                    'image_path': rec['image_path'],
                    'chunk': idx,
                })
        stored = store.upsert_chunks(user_id=request.user.id, document_id=doc.id, chunks=chunks)
        return Response({'document': DocumentSerializer(doc).data, 'chunks_indexed': stored}, status=201)

class DocumentDetailView(APIView):
    def delete(self, request, pk):
        try:
            doc = Document.objects.get(pk=pk, owner=request.user)
        except Document.DoesNotExist:
            return Response(status=404)
        # delete from chroma
        ChromaStore().delete_document(user_id=request.user.id, document_id=doc.id)
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=204)

class ConversationListCreateView(APIView):
    def get(self, request):
        convos = Conversation.objects.filter(owner=request.user).order_by('-created_at')
        return Response(ConversationSerializer(convos, many=True).data)

    def post(self, request):
        title = request.data.get('title','')
        c = Conversation.objects.create(owner=request.user, title=title)
        return Response(ConversationSerializer(c).data, status=201)
    
    def delete(self, request, convo_id):
        try:
            convo = Conversation.objects.get(pk=convo_id, owner=request.user)
        except Conversation.DoesNotExist:
            return Response(status=404)
        # delete all messages and sources
        MessageSource.objects.filter(message__conversation=convo).delete()
        Message.objects.filter(conversation=convo).delete()
        convo.delete()
        return Response(status=204)
    
    def put(self, request, convo_id):
        try:
            convo = Conversation.objects.get(pk=convo_id, owner=request.user)
        except Conversation.DoesNotExist:
            return Response(status=404)
        convo.title = request.data.get('title','')
        convo.save()
        return Response(ConversationSerializer(convo).data)


class MessageCreateView(APIView):
    def post(self, request, convo_id):
        try:
            convo = Conversation.objects.get(pk=convo_id, owner=request.user)
        except Conversation.DoesNotExist:
            return Response(status=404)

        user_text = request.data.get('message','').strip()
        if not user_text:
            return Response({'detail':'message required'}, status=400)
        
        # NEW: accept a single id or a list
        doc_ids = request.data.get('document_ids', None)  # e.g., [12, 34]
        if not doc_ids:
            single = request.data.get('document_id', None)  # e.g., 12
            if single is not None and str(single).strip() != '':
                doc_ids = [int(single)]

        # (optional) safety: ensure provided doc_ids belong to this user
        if doc_ids:
            owned = set(
                Document.objects.filter(owner=request.user, id__in=doc_ids).values_list('id', flat=True)
            )
            doc_ids = [int(d) for d in doc_ids if int(d) in owned]
            if not doc_ids:
                return Response({'detail': 'No matching documents owned by user.'}, status=400)        

        # store user msg
        m_user = Message.objects.create(conversation=convo, role='user', content=user_text)

        # retrieve
        store = ChromaStore()
        hits = store.query(user_id=request.user.id, text=user_text, top_k=int(request.data.get('top_k',8)), document_ids=doc_ids)

        # synthesize answer
        answer = synthesize_answer(user_text, hits)
        m_assist = Message.objects.create(conversation=convo, role='assistant', content=answer)

        # track sources (first few)
        for h in hits[:5]:
            # Best-effort mapping to Document by filename
            doc = None
            try:
                src_name = os.path.basename(str(h.get('source','')))
                doc = Document.objects.filter(owner=request.user, original_name__icontains=src_name).first()
            except Exception:
                doc = None
            MessageSource.objects.create(
                message=m_assist,
                document=doc,
                page=h.get('page',0),
                snippet=(h.get('text') or '')[:500],
                image_path=h.get('image_path',''),
                source=h.get('source',''),
            )

        return Response({
            'assistant': MessageSerializer(m_assist).data,
            'retrieved': hits,
        }, status=201)

class ConversationDetailView(APIView):
    def get(self, request, convo_id):
        try:
            convo = Conversation.objects.get(pk=convo_id, owner=request.user)
        except Conversation.DoesNotExist:
            return Response(status=404)
        msgs = convo.messages.order_by('created_at')
        return Response({
            'conversation': ConversationSerializer(convo).data,
            'messages': MessageSerializer(msgs, many=True).data,
        })
