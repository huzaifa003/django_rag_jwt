from django.urls import path
from .views import (
    RegisterView, SendVerificationEmailView, VerifyEmailView,
    PasswordResetRequestView, PasswordResetConfirmView, ChangePasswordView,
    UserProfileView, ProfilePictureView, UpdateLLMModelView,
    DocumentListCreateView, DocumentDetailView,
    ConversationListCreateView, ConversationDetailView, MessageCreateView,
)
from rest_framework.permissions import AllowAny
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/send-verification-email/', SendVerificationEmailView.as_view(), name='send-verification-email'),
    path('auth/verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    path('auth/password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('profile/picture/', ProfilePictureView.as_view(), name='profile-picture'),
    path('user/update-llm-model/', UpdateLLMModelView.as_view(), name='update-llm-model'),
    path('docs/', DocumentListCreateView.as_view(), name='docs'),
    path('docs/<int:pk>/', DocumentDetailView.as_view(), name='doc-detail'),
    path('conversations/', ConversationListCreateView.as_view(), name='conversations'),
    path('conversations/<int:convo_id>/', ConversationDetailView.as_view(), name='conversation-detail'),
    path('conversations/<int:convo_id>/messages/', MessageCreateView.as_view(), name='message-create'),
]

@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    return Response({'ok': True})

urlpatterns += [ path('health/', health) ]
