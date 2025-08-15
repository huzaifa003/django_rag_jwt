from django.contrib import admin
from .models import Document, Conversation, Message, MessageSource

admin.site.register(Document)
admin.site.register(Conversation)
admin.site.register(Message)
admin.site.register(MessageSource)
