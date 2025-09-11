import requests
from bs4 import BeautifulSoup
import json
from django.db import transaction
from content.models import Lesson, Module

class ContentIntegrator:
    def __init__(self):
        self.sources = {
            'w3schools': {
                'base_url': 'https://www.w3schools.com',
                'topics': {
                    'cpp': 'cpp/default.asp',
                    'python': 'python/default.asp',
                    'html': 'html/default.asp',
                    'css': 'css/default.asp',
                    'js': 'js/default.asp',
                }
            }
        }
    
    def fetch_and_integrate_content(self, topic, course):
        """Fetch content from external sources and integrate into our system"""
        if topic not in self.sources['w3schools']['topics']:
            return None
        
        try:
            url = f"{self.sources['w3schools']['base_url']}/{self.sources['w3schools']['topics'][topic]}"
            response = requests.get(url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract main content
            main_content = soup.find('div', {'id': 'main'})
            
            if not main_content:
                return None
            
            # Create a new module for this external content
            module, created = Module.objects.get_or_create(
                course=course,
                title=f"W3Schools {topic.upper()} Reference",
                defaults={
                    'description': f"External reference content from W3Schools for {topic.upper()}",
                    'order': 999,  # Place at the end
                    'is_external': True
                }
            )
            
            # Extract and create lessons from the content
            lessons_created = []
            for i, section in enumerate(main_content.find_all(['h2', 'h3'])[:10]):  # Limit to 10 sections
                title = section.get_text().strip()
                content = self.extract_section_content(section)
                
                if content:
                    lesson, created = Lesson.objects.get_or_create(
                        module=module,
                        title=title,
                        defaults={
                            'content': content,
                            'order': i,
                            'content_type': 'text',
                            'difficulty': 'intermediate',
                            'topics': topic,
                            'is_external': True,
                            'external_url': url
                        }
                    )
                    lessons_created.append(lesson)
            
            return {
                'module': module,
                'lessons': lessons_created
            }
            
        except Exception as e:
            print(f"Error fetching content from W3Schools: {e}")
            return None
    
    def extract_section_content(self, section_element):
        """Extract content from a section element"""
        content = []
        next_element = section_element.next_sibling
        
        while next_element and next_element.name not in ['h2', 'h3', 'h1']:
            if next_element.name in ['p', 'div', 'pre']:
                content.append(str(next_element))
            next_element = next_element.next_sibling
        
        return ''.join(content) if content else None

# Initialize content integrator
content_integrator = ContentIntegrator()