import os
from django.conf import settings
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import CustomUser, Document, Conversation, Message, MessageSource
from .serializers import (
    RegisterSerializer, CustomTokenObtainPairSerializer, DocumentSerializer, ConversationSerializer, MessageSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer, ChangePasswordSerializer,
    UserProfileSerializer, UserProfileUpdateSerializer, ProfilePictureSerializer
)
from .extract import extract_pdf_pages_as_images
from .openai_helpers import vision_extract, synthesize_answer
from .textutils import split_for_embedding
from .store import ChromaStore
from .email_service import (
    create_verification_token, send_verification_email, verify_email_token,
    create_password_reset_token, send_password_reset_email, verify_password_reset_token, use_password_reset_token
)

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

class RegisterView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    
    def perform_create(self, serializer):
        user = serializer.save()
        # Create and send verification email
        verification_token = create_verification_token(user)
        send_verification_email(user, verification_token)

class SendVerificationEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'detail': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = CustomUser.objects.get(email=email)
            
            if user.email_verified:
                return Response({'detail': 'Email is already verified'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Create and send new verification email
            verification_token = create_verification_token(user)
            email_sent = send_verification_email(user, verification_token)
            
            if email_sent:
                return Response({
                    'detail': 'Verification email sent successfully',
                    'message': 'Please check your email and click the verification link.'
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'detail': 'Failed to send verification email'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except CustomUser.DoesNotExist:
            return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        token = request.data.get('token')
        if not token:
            return Response({'detail': 'Token is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        success, message = verify_email_token(token)
        
        if success:
            return Response({
                'detail': message,
                'email_verified': True
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'detail': message,
                'email_verified': False
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def get(self, request):
        email = request.query_params.get('email')
        if not email:
            return Response({'detail': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = CustomUser.objects.get(email=email)
            return Response({
                'email': user.email,
                'email_verified': user.email_verified
            }, status=status.HTTP_200_OK)
            
        except CustomUser.DoesNotExist:
            return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

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
        convos = Conversation.objects.filter(owner=request.user).order_by('-updated_at')
        return Response(ConversationSerializer(convos, many=True).data)

    def post(self, request):
        title = request.data.get('title','')
        c = Conversation.objects.create(owner=request.user, title=title)
        return Response(ConversationSerializer(c).data, status=201)
    
    


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

        # Update conversation's updated_at field to reflect the new message
        from django.utils import timezone
        convo.updated_at = timezone.now()
        convo.save()

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

class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            
            try:
                user = CustomUser.objects.get(email=email)
                
                # Create and send password reset email
                reset_token = create_password_reset_token(user, expires_in_hours=1)
                email_sent = send_password_reset_email(user, reset_token)
                
                if email_sent:
                    return Response({
                        'detail': 'Password reset email sent successfully',
                        'message': 'Please check your email and click the reset link.'
                    }, status=status.HTTP_200_OK)
                else:
                    return Response({
                        'detail': 'Failed to send password reset email'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                    
            except CustomUser.DoesNotExist:
                # Don't reveal if user exists or not for security
                return Response({
                    'detail': 'If an account with that email exists, a password reset link has been sent.'
                }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            token = serializer.validated_data['token']
            new_password = serializer.validated_data['new_password']
            
            # Verify token
            success, result = verify_password_reset_token(token)
            
            if not success:
                return Response({
                    'detail': result
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user = result
            
            # Update password
            user.set_password(new_password)
            user.save()
            
            # Mark token as used
            use_password_reset_token(token)
            
            return Response({
                'detail': 'Password reset successfully'
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            old_password = serializer.validated_data['old_password']
            new_password = serializer.validated_data['new_password']
            
            # Verify old password
            if not request.user.check_password(old_password):
                return Response({
                    'detail': 'Current password is incorrect'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Update password
            request.user.set_password(new_password)
            request.user.save()
            
            return Response({
                'detail': 'Password changed successfully'
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get user profile information"""
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)
    
    def put(self, request):
        """Update user profile information"""
        serializer = UserProfileUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            # Return updated profile
            profile_serializer = UserProfileSerializer(request.user)
            return Response(profile_serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ProfilePictureView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)
    
    def post(self, request):
        """Upload/Update profile picture"""
        serializer = ProfilePictureSerializer(request.user, data=request.data)
        if serializer.is_valid():
            # Delete old profile picture if exists
            if request.user.profile_picture:
                request.user.profile_picture.delete(save=False)
            
            serializer.save()
            
            # Return updated profile
            profile_serializer = UserProfileSerializer(request.user)
            return Response({
                'detail': 'Profile picture updated successfully',
                'profile': profile_serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request):
        """Remove profile picture"""
        if request.user.profile_picture:
            request.user.profile_picture.delete(save=False)
            request.user.profile_picture = None
            request.user.save()
            
            profile_serializer = UserProfileSerializer(request.user)
            return Response({
                'detail': 'Profile picture removed successfully',
                'profile': profile_serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response({
            'detail': 'No profile picture to remove'
        }, status=status.HTTP_400_BAD_REQUEST)

class UpdateLLMModelView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get user's current LLM model preference"""
        return Response({
            'preferred_llm': request.user.preferred_llm,
            'current_model_details': {
                'name': request.user.preferred_llm,
                'display_name': dict(request.user.LLM_CHOICES).get(request.user.preferred_llm, 'Unknown')
            }
        })
    
    def post(self, request):
        """Update user's LLM model preference"""
        preferred_llm = request.data.get('preferred_llm')
        
        if not preferred_llm:
            return Response({
                'detail': 'preferred_llm is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate the model choice
        valid_choices = [choice[0] for choice in request.user.LLM_CHOICES]
        if preferred_llm not in valid_choices:
            return Response({
                'detail': f'Invalid model choice. Must be one of: {", ".join(valid_choices)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Update the user's preference
        request.user.preferred_llm = preferred_llm
        request.user.save()
        
        return Response({
            'detail': 'LLM model preference updated successfully',
            'preferred_llm': request.user.preferred_llm,
            'current_model_details': {
                'name': request.user.preferred_llm,
                'display_name': dict(request.user.LLM_CHOICES).get(request.user.preferred_llm, 'Unknown')
            }
        }, status=status.HTTP_200_OK)
