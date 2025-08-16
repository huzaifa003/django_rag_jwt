from django.contrib import admin
from .models import Document, Conversation, Message, CustomUser, UserSession, EmailVerificationToken, PasswordResetToken, MessageSource

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
	list_display = ('email', 'first_name', 'last_name', 'email_verified', 'is_active_session', 'date_joined')
	list_filter = ('email_verified', 'is_active_session', 'gender', 'date_joined')
	search_fields = ('email', 'first_name', 'last_name')
	readonly_fields = ('date_joined', 'last_login')

@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
	list_display = ('user', 'ip_address', 'created_at', 'last_activity', 'expires_at', 'is_active')
	list_filter = ('is_active', 'created_at', 'expires_at')
	search_fields = ('user__email', 'ip_address')
	readonly_fields = ('created_at', 'last_activity')
	date_hierarchy = 'created_at'

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
	list_display = ('original_name', 'owner', 'created_at')
	list_filter = ('created_at',)
	search_fields = ('original_name', 'owner__email')
	readonly_fields = ('created_at',)

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
	list_display = ('title', 'owner', 'created_at')
	list_filter = ('created_at',)
	search_fields = ('title', 'owner__email')
	readonly_fields = ('created_at',)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
	list_display = ('conversation', 'role', 'content_preview', 'created_at')
	list_filter = ('role', 'created_at')
	search_fields = ('content', 'conversation__title')
	readonly_fields = ('created_at',)
	
	def content_preview(self, obj):
		return obj.content[:100] + '...' if len(obj.content) > 100 else obj.content
	content_preview.short_description = 'Content Preview'

@admin.register(MessageSource)
class MessageSourceAdmin(admin.ModelAdmin):
	list_display = ('message', 'document', 'page', 'source')
	list_filter = ('page',)
	search_fields = ('source', 'snippet')
	readonly_fields = ()

@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
	list_display = ('user', 'created_at', 'expires_at', 'is_used')
	list_filter = ('is_used', 'created_at', 'expires_at')
	search_fields = ('user__email',)
	readonly_fields = ('created_at',)

@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
	list_display = ('user', 'created_at', 'expires_at', 'is_used')
	list_filter = ('is_used', 'created_at', 'expires_at')
	search_fields = ('user__email',)
	readonly_fields = ('created_at',)
