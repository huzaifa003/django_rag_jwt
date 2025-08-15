from django.db import models
from django.contrib.auth.models import User

class Document(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='docs/')
    original_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.original_name} (u{self.owner_id})"

class Conversation(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title or 'Conversation'} (u{self.owner_id})"

class Message(models.Model):
    ROLE_CHOICES = (('user','user'),('assistant','assistant'))
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

class MessageSource(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='sources')
    document = models.ForeignKey(Document, on_delete=models.SET_NULL, null=True, blank=True)
    page = models.IntegerField(default=0)
    snippet = models.TextField(blank=True, default='')
    image_path = models.TextField(blank=True, default='')
    source = models.TextField(blank=True, default='')  # file path or name
