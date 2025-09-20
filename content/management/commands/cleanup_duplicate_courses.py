# Create a management command to clean up duplicates
# In management/commands/cleanup_duplicate_courses.py

from django.core.management.base import BaseCommand
from content.models import GeneratedCourse
from django.db.models import Count

class Command(BaseCommand):
    help = 'Clean up duplicate generated courses'

    def handle(self, *args, **options):
        # Find duplicate courses (same user and title)
        duplicates = GeneratedCourse.objects.values('user', 'title').annotate(
            count=Count('id')
        ).filter(count__gt=1)

        for duplicate in duplicates:
            user_id = duplicate['user']
            title = duplicate['title']
            
            # Get all duplicate courses for this user and title
            courses = GeneratedCourse.objects.filter(
                user_id=user_id, 
                title=title
            ).order_by('created_at')
            
            # Keep the first one, delete the rest
            keep_course = courses.first()
            delete_courses = courses.exclude(id=keep_course.id)
            
            self.stdout.write(
                self.style.WARNING(
                    f"Found {delete_courses.count()} duplicates for user {user_id}, course '{title}'"
                )
            )
            
            # Delete the duplicates
            delete_count, _ = delete_courses.delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Deleted {delete_count} duplicate courses for user {user_id}, course '{title}'"
                )
            )