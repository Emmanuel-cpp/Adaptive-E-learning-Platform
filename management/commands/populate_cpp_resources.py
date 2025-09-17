# management/commands/populate_cpp_resources.py
from django.core.management.base import BaseCommand
from content.models import CppLearningResource

class Command(BaseCommand):
    help = 'Populates the database with C++ learning resources'
    
    def handle(self, *args, **options):
        resources = [
            {
                'title': 'C++ Tutorial for Beginners',
                'url': 'https://www.w3schools.com/cpp/',
                'resource_type': 'tutorial',
                'topic_category': 'syntax',
                'difficulty': 'basic',
                'description': 'Learn C++ basics with interactive examples',
                'source': 'W3Schools'
            },
            {
                'title': 'C++ Object-Oriented Programming',
                'url': 'https://www.learncpp.com/cpp-tutorial/classes-and-objects/',
                'resource_type': 'tutorial',
                'topic_category': 'oop',
                'difficulty': 'intermediate',
                'description': 'Comprehensive guide to OOP in C++',
                'source': 'LearnCpp'
            },
            # Add more resources as needed
        ]
        
        for resource_data in resources:
            resource, created = CppLearningResource.objects.get_or_create(
                title=resource_data['title'],
                defaults=resource_data
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created resource: {resource.title}'))
            else:
                self.stdout.write(self.style.WARNING(f'Resource already exists: {resource.title}'))