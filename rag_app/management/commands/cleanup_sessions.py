from django.core.management.base import BaseCommand
from django.utils import timezone
from rag_app.models import UserSession, CustomUser


class Command(BaseCommand):
	help = 'Clean up expired user sessions'

	def add_arguments(self, parser):
		parser.add_argument(
			'--dry-run',
			action='store_true',
			help='Show what would be cleaned up without actually doing it',
		)

	def handle(self, *args, **options):
		dry_run = options['dry_run']
		
		if dry_run:
			self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
		
		# Get expired sessions
		expired_sessions = UserSession.objects.filter(
			expires_at__lt=timezone.now(),
			is_active=True
		)
		
		expired_count = expired_sessions.count()
		self.stdout.write(f"Found {expired_count} expired sessions")
		
		if expired_count == 0:
			self.stdout.write(self.style.SUCCESS('No expired sessions to clean up'))
			return
		
		if not dry_run:
			# Get users who will have no active sessions after cleanup
			users_with_expired_sessions = expired_sessions.values_list('user_id', flat=True).distinct()
			users_to_update = []
			
			for user_id in users_with_expired_sessions:
				if not UserSession.objects.filter(
					user_id=user_id, 
					is_active=True, 
					expires_at__gt=timezone.now()
				).exists():
					users_to_update.append(user_id)
			
			# Update users who have no active sessions
			if users_to_update:
				CustomUser.objects.filter(id__in=users_to_update).update(
					is_active_session=False,
					session_created_at=None,
					session_expires_at=None
				)
				self.stdout.write(f"Updated {len(users_to_update)} users with no active sessions")
			
			# Deactivate expired sessions
			expired_sessions.update(is_active=False)
			
			self.stdout.write(
				self.style.SUCCESS(f'Successfully cleaned up {expired_count} expired sessions')
			)
		else:
			# Show what would be cleaned up
			for session in expired_sessions[:10]:  # Show first 10
				self.stdout.write(f"Would deactivate: {session.user.email} - {session.created_at}")
			
			if expired_count > 10:
				self.stdout.write(f"... and {expired_count - 10} more sessions")
