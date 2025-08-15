from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Document, Conversation, Message, MessageSource

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    class Meta:
        model = User
        fields = ('id','username','email','password')
    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email',''),
            password=validated_data['password']
        )
        return user

class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ('id','original_name','file','created_at')

class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ('id','title','created_at')

class MessageSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageSource
        fields = ('page','snippet','image_path','source','document')

class MessageSerializer(serializers.ModelSerializer):
    sources = MessageSourceSerializer(many=True, read_only=True)
    class Meta:
        model = Message
        fields = ('id','role','content','created_at','sources')
