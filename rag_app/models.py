from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone
import secrets

class CustomUserManager(BaseUserManager):
	def create_user(self, email, password=None, **extra_fields):
		if not email:
			raise ValueError('The Email field must be set')
		email = self.normalize_email(email)
		user = self.model(email=email, **extra_fields)
		user.set_password(password)
		user.save(using=self._db)
		return user

	def create_superuser(self, email, password=None, **extra_fields):
		extra_fields.setdefault('is_staff', True)
		extra_fields.setdefault('is_superuser', True)
		extra_fields.setdefault('email_verified', True)

		if extra_fields.get('is_staff') is not True:
			raise ValueError('Superuser must have is_staff=True.')
		if extra_fields.get('is_superuser') is not True:
			raise ValueError('Superuser must have is_superuser=True.')

		return self.create_user(email, password, **extra_fields)

class CustomUser(AbstractUser):
	username = None
	email = models.EmailField(unique=True)
	email_verified = models.BooleanField(default=False)
	profile_picture = models.ImageField(upload_to='profile_pictures/', null=True, blank=True)
	bio = models.TextField(max_length=500, blank=True)
	phone_number = models.CharField(max_length=15, blank=True)
	date_of_birth = models.DateField(null=True, blank=True)
	
	GENDER_CHOICES = [
		('M', 'Male'),
		('F', 'Female'),
		('O', 'Other'),
		('P', 'Prefer not to say'),
	]
	gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
	address = models.TextField(max_length=200, blank=True)
	
	# LLM Model preference
	LLM_CHOICES = [
		('openai', 'OpenAI GPT'),
		('gemini', 'Google Gemini'),
	]
	preferred_llm = models.CharField(max_length=10, choices=LLM_CHOICES, default='openai')
	
	# Session tracking fields
	last_login_ip = models.GenericIPAddressField(null=True, blank=True)
	last_login_device = models.CharField(max_length=255, blank=True)
	is_active_session = models.BooleanField(default=False)
	session_created_at = models.DateTimeField(null=True, blank=True)
	session_expires_at = models.DateTimeField(null=True, blank=True)

	objects = CustomUserManager()

	USERNAME_FIELD = 'email'
	REQUIRED_FIELDS = ['first_name', 'last_name']

	def __str__(self):
		return self.email

	@property
	def full_name(self):
		return f"{self.first_name} {self.last_name}"

	@property
	def gender_display(self):
		return dict(self.GENDER_CHOICES).get(self.gender, '')

class UserSession(models.Model):
	user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='sessions')
	session_token = models.CharField(max_length=255, unique=True)
	refresh_token = models.CharField(max_length=255, unique=True)
	ip_address = models.GenericIPAddressField(null=True, blank=True)
	user_agent = models.CharField(max_length=500, blank=True)
	device_info = models.CharField(max_length=255, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	last_activity = models.DateTimeField(auto_now=True)
	expires_at = models.DateTimeField()
	is_active = models.BooleanField(default=True)
	
	class Meta:
		db_table = 'user_sessions'
		indexes = [
			models.Index(fields=['user', 'is_active']),
			models.Index(fields=['session_token']),
			models.Index(fields=['refresh_token']),
			models.Index(fields=['expires_at']),
		]

	def __str__(self):
		return f"{self.user.email} - {self.created_at}"

	@property
	def is_expired(self):
		return timezone.now() > self.expires_at

	def refresh_session(self, new_expires_at):
		"""Refresh the session with new expiration time"""
		self.expires_at = new_expires_at
		self.last_activity = timezone.now()
		self.save()

	def deactivate(self):
		"""Deactivate the session"""
		self.is_active = False
		self.save()

	@classmethod
	def create_session(cls, user, session_token, refresh_token, ip_address=None, user_agent=None, expires_at=None):
		"""Create a new user session"""
		if expires_at is None:
			expires_at = timezone.now() + timezone.timedelta(days=1)  # 24 hours default
		
		# Deactivate all existing sessions for this user
		cls.objects.filter(user=user, is_active=True).update(is_active=False)
		
		# Create new session
		session = cls.objects.create(
			user=user,
			session_token=session_token,
			refresh_token=refresh_token,
			ip_address=ip_address,
			user_agent=user_agent,
			expires_at=expires_at
		)
		
		# Update user's session info
		user.is_active_session = True
		user.session_created_at = timezone.now()
		user.session_expires_at = expires_at
		user.save()
		
		return session

	@classmethod
	def get_valid_session(cls, session_token):
		"""Get a valid session by token"""
		try:
			session = cls.objects.get(
				session_token=session_token,
				is_active=True,
				expires_at__gt=timezone.now()
			)
			# Update last activity
			session.last_activity = timezone.now()
			session.save()
			return session
		except cls.DoesNotExist:
			return None

	@classmethod
	def get_valid_refresh_session(cls, refresh_token):
		"""Get a valid session by refresh token"""
		try:
			session = cls.objects.get(
				refresh_token=refresh_token,
				is_active=True,
				expires_at__gt=timezone.now()
			)
			return session
		except cls.DoesNotExist:
			return None

	@classmethod
	def cleanup_expired_sessions(cls):
		"""Clean up expired sessions"""
		expired_sessions = cls.objects.filter(
			expires_at__lt=timezone.now(),
			is_active=True
		)
		
		# Update users who have no active sessions
		users_with_expired_sessions = expired_sessions.values_list('user_id', flat=True).distinct()
		for user_id in users_with_expired_sessions:
			if not cls.objects.filter(user_id=user_id, is_active=True, expires_at__gt=timezone.now()).exists():
				CustomUser.objects.filter(id=user_id).update(
					is_active_session=False,
					session_created_at=None,
					session_expires_at=None
				)
		
		# Deactivate expired sessions
		expired_sessions.update(is_active=False)

class Document(models.Model):
    owner = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='docs/')
    original_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.original_name} (u{self.owner_id})"

class Conversation(models.Model):
    owner = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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

class EmailVerificationToken(models.Model):
	user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='email_verification_tokens')
	token = models.CharField(max_length=255, unique=True)
	created_at = models.DateTimeField(auto_now_add=True)
	expires_at = models.DateTimeField()
	is_used = models.BooleanField(default=False)
	
	def __str__(self):
		return f"Email verification for {self.user.email}"
	
	def is_expired(self):
		from django.utils import timezone
		return timezone.now() > self.expires_at

class PasswordResetToken(models.Model):
	user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='password_reset_tokens')
	token = models.CharField(max_length=255, unique=True)
	created_at = models.DateTimeField(auto_now_add=True)
	expires_at = models.DateTimeField()
	is_used = models.BooleanField(default=False)
	
	def __str__(self):
		return f"Password reset for {self.user.email}"
	
	def is_expired(self):
		from django.utils import timezone
		return timezone.now() > self.expires_at
