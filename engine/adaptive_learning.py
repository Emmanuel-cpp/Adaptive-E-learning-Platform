import numpy as np
from django.db import transaction
from django.utils import timezone
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
import json
from datetime import timedelta

from engine.models import StudentProfile, ContentRecommendation, LearningPath
from users.models import Student
from content.models import Lesson, Module, Course
from progress.models import ModuleProgress, UserProgress

class AdaptiveLearningEngine:
    def __init__(self):
        self.student_profiles = {}
        self.content_recommendations = {}
        self.learning_paths = {}
        
    def get_or_create_profile(self, student):
        """Get or create a student profile"""
        profile, created = StudentProfile.objects.get_or_create(
            student=student,
            defaults={
                'learning_style': student.learning_style,
                'mastery_level': student.mastery_level,
                'knowledge_gaps': [],
                'strengths': [],
                'learning_patterns': {}
            }
        )
        return profile
    
    def analyze_assessment_results(self, student, assessment_data):
        """Analyze assessment results to identify knowledge gaps"""
        with transaction.atomic():
            profile = self.get_or_create_profile(student)
            
            # Extract topics and scores from assessment data
            knowledge_gaps = []
            strengths = []
            
            for topic, score in assessment_data.items():
                if score < 0.7:  # If score below 70%
                    knowledge_gaps.append({'topic': topic, 'score': score})
                elif score > 0.85:  # If score above 85%
                    strengths.append({'topic': topic, 'score': score})
            
            profile.knowledge_gaps = knowledge_gaps
            profile.strengths = strengths
            profile.save()
            
            # Update recommendations based on new analysis
            self.update_recommendations(student)
            
            return knowledge_gaps, strengths
    
    def update_recommendations(self, student):
        """Update content recommendations based on student profile"""
        profile = self.get_or_create_profile(student)
        
        # Clear existing recommendations
        ContentRecommendation.objects.filter(student=student).delete()
        
        recommendations = []
        
        # Recommend content based on knowledge gaps
        for gap in profile.knowledge_gaps:
            content_items = self.find_content_for_topic(gap['topic'], profile.learning_style)
            for content in content_items:
                recommendation = ContentRecommendation(
                    student=student,
                    content=content,
                    reason=f"Addressing knowledge gap in {gap['topic']} (score: {gap['score']*100:.1f}%)",
                    priority=5  # High priority for knowledge gaps
                )
                recommendations.append(recommendation)
        
        # Recommend challenging content for strengths
        for strength in profile.strengths:
            content_items = self.find_advanced_content(strength['topic'], profile.learning_style)
            for content in content_items:
                recommendation = ContentRecommendation(
                    student=student,
                    content=content,
                    reason=f"Building on strength in {strength['topic']} (score: {strength['score']*100:.1f}%)",
                    priority=3  # Medium priority for strengths
                )
                recommendations.append(recommendation)
        
        # Bulk create recommendations
        ContentRecommendation.objects.bulk_create(recommendations)
        
        return recommendations
    
    def find_content_for_topic(self, topic, learning_style):
        """Find appropriate content for a specific topic and learning style"""
        # Search for lessons with matching topics
        lessons = Lesson.objects.filter(
            topics__icontains=topic,
            difficulty__in=['beginner', 'intermediate']
        )
        
        # Filter by learning style preference
        if learning_style == 'visual':
            lessons = lessons.filter(content_type__in=['video', 'interactive'])
        elif learning_style == 'auditory':
            lessons = lessons.filter(content_type__in=['audio', 'interactive'])
        elif learning_style == 'kinesthetic':
            lessons = lessons.filter(content_type__in=['interactive', 'exercise'])
        
        return lessons[:3]  # Return top 3 matches
    
    def find_advanced_content(self, topic, learning_style):
        """Find advanced content for a specific topic"""
        # Search for advanced lessons with matching topics
        lessons = Lesson.objects.filter(
            topics__icontains=topic,
            difficulty='advanced'
        )
        
        # Filter by learning style preference
        if learning_style == 'visual':
            lessons = lessons.filter(content_type__in=['video', 'interactive'])
        elif learning_style == 'auditory':
            lessons = lessons.filter(content_type__in=['audio', 'interactive'])
        elif learning_style == 'kinesthetic':
            lessons = lessons.filter(content_type__in=['interactive', 'exercise'])
        
        return lessons[:2]  # Return top 2 matches
    
    def generate_learning_path(self, student, course):
        """Generate a personalized learning path for a student"""
        profile = self.get_or_create_profile(student)
        
        # Get all modules in the course
        modules = Module.objects.filter(course=course).order_by('order')
        
        # Create a custom path based on student's profile
        path = []
        for module in modules:
            path.append(module.id)
        
        # Adjust path based on knowledge gaps - move relevant modules earlier
        knowledge_gap_topics = [gap['topic'] for gap in profile.knowledge_gaps]
        
        for i, module_id in enumerate(path):
            module = Module.objects.get(id=module_id)
            module_topics = module.topics.split(',') if module.topics else []
            
            # Check if this module addresses any knowledge gaps
            if any(topic in knowledge_gap_topics for topic in module_topics):
                # Move this module earlier in the path
                if i > 0:
                    path.pop(i)
                    path.insert(0, module_id)
        
        # Create or update learning path
        learning_path, created = LearningPath.objects.get_or_create(
            student=student,
            course=course,
            defaults={
                'path': path,
                'estimated_completion_time': self.estimate_completion_time(student, course, path)
            }
        )
        
        if not created:
            learning_path.path = path
            learning_path.estimated_completion_time = self.estimate_completion_time(student, course, path)
            learning_path.save()
        
        return learning_path
    
    def estimate_completion_time(self, student, course, path):
        """Estimate time to complete the course based on student's learning patterns"""
        # Simple estimation - could be enhanced with more sophisticated algorithm
        base_time = timedelta(hours=10)  # Base time for the course
        
        # Adjust based on student's mastery level
        profile = self.get_or_create_profile(student)
        if profile.mastery_level == 'beginner':
            base_time *= 1.5
        elif profile.mastery_level == 'advanced':
            base_time *= 0.7
        
        return base_time

# Initialize the AI engine
ai_engine = AdaptiveLearningEngine()

def get_next_lesson(student, current_lesson):
    """
    Get the next recommended lesson for a student based on their learning path
    """
    try:
        # Get the course from the current lesson's module
        course = current_lesson.module.course
        
        # Get the student's learning path
        learning_path = LearningPath.objects.filter(student=student, course=course).first()
        
        if not learning_path:
            # Generate a learning path if none exists
            learning_path = ai_engine.generate_learning_path(student, course)
        
        # First, try to find the next lesson in the same module
        next_lesson_same_module = Lesson.objects.filter(
            module=current_lesson.module,
            order__gt=current_lesson.order
        ).order_by('order').first()
        
        if next_lesson_same_module:
            return next_lesson_same_module
        
        # If no more lessons in current module, find the next module that has lessons
        current_module = current_lesson.module
        
        # Get all modules in the course, ordered properly
        all_modules = list(course.modules.all().order_by('order'))
        
        try:
            # Find the current module's position
            current_index = all_modules.index(current_module)
            
            # Find the next module that has lessons
            for i in range(current_index + 1, len(all_modules)):
                next_module = all_modules[i]
                first_lesson = next_module.lesson_set.order_by('order').first()
                if first_lesson:
                    return first_lesson
                    
        except ValueError:
            # Current module not found in all_modules list
            pass
            
        return None
            
    except Exception as e:
        print(f"Error getting next lesson: {e}")
        # Fallback to simple linear navigation
        try:
            # Check if there's a next lesson in the same module
            next_lesson = Lesson.objects.filter(
                module=current_lesson.module,
                order__gt=current_lesson.order
            ).order_by('order').first()
            
            if next_lesson:
                return next_lesson
            
            # If no more lessons in current module, find the next module with lessons
            all_modules = list(Module.objects.filter(
                course=current_lesson.module.course
            ).order_by('order'))
            
            try:
                current_index = all_modules.index(current_lesson.module)
                
                # Find the next module that has lessons
                for i in range(current_index + 1, len(all_modules)):
                    next_module = all_modules[i]
                    first_lesson = next_module.lesson_set.order_by('order').first()
                    if first_lesson:
                        return first_lesson
            except ValueError:
                pass
                
        except Exception as fallback_error:
            print(f"Fallback navigation also failed: {fallback_error}")
        
        return None

def get_previous_lesson(student, current_lesson):
    """
    Get the previous lesson for a student based on their learning path
    """
    try:
        # Get the course from the current lesson's module
        course = current_lesson.module.course
        
        # First, try to find the previous lesson in the same module
        previous_lesson_same_module = Lesson.objects.filter(
            module=current_lesson.module,
            order__lt=current_lesson.order
        ).order_by('-order').first()
        
        if previous_lesson_same_module:
            return previous_lesson_same_module
        
        # If no previous lesson in current module, find the previous module
        # Get the student's learning path
        learning_path = LearningPath.objects.filter(student=student, course=course).first()
        
        if not learning_path:
            # Generate a learning path if none exists
            learning_path = ai_engine.generate_learning_path(student, course)
        
        current_module = current_lesson.module
        
        if current_module.id not in learning_path.path:
            # Current module not in path, use simple linear navigation
            all_modules = list(course.modules.all().order_by('order'))
            try:
                current_index = all_modules.index(current_module)
                if current_index > 0:
                    prev_module = all_modules[current_index - 1]
                    return prev_module.lesson_set.order_by('-order').first()
            except ValueError:
                pass
            return None
        
        current_position = learning_path.path.index(current_module.id)
        
        if current_position > 0:
            # Get the previous module in the path
            prev_module_id = learning_path.path[current_position - 1]
            prev_module = Module.objects.get(id=prev_module_id)
            
            # Return the last lesson in the previous module
            return prev_module.lesson_set.order_by('-order').first()
        else:
            # Student is at the beginning of the path
            return None
            
    except Exception as e:
        print(f"Error getting previous lesson: {e}")
        # Fallback to simple linear navigation
        try:
            previous_lesson = Lesson.objects.filter(
                module=current_lesson.module,
                order__lt=current_lesson.order
            ).order_by('-order').first()
            
            if previous_lesson:
                return previous_lesson
            
            # If no previous lessons in current module, get last lesson of previous module
            prev_module = Module.objects.filter(
                course=current_lesson.module.course,
                order__lt=current_lesson.module.order
            ).order_by('-order').first()
            
            if prev_module:
                return prev_module.lesson_set.order_by('-order').first()
        except Exception as fallback_error:
            print(f"Fallback navigation also failed: {fallback_error}")
        
        return None 
    
"""def get_lesson_recommendations(student, lesson):
    #Get AI-powered recommendations for a specific lesson
    # Get or create the student's learning profile
    profile = get_or_create_profile(student)
    
    recommendations = []
    
    # Recommend additional resources based on lesson topics
    lesson_topics = lesson.topics.split(',') if lesson.topics else []
    
    for topic in lesson_topics:
        topic = topic.strip()
        if topic:
            # Find related content (without using self)
            related_content = find_content_for_topic(topic, profile.learning_style)
            for content in related_content:
                recommendations.append({
                    'title': content.title,
                    'type': content.content_type,
                    'difficulty': content.difficulty,
                    'reason': f"Deepen your understanding of {topic}",
                    'link': f"/content/lesson/{content.id}/"
                })
    
    # Recommend practice exercises if lesson isn’t interactive
    if lesson.content_type != 'interactive' and lesson_topics:
        practice_lessons = Lesson.objects.filter(
            module__course=lesson.module.course,
            content_type='interactive',
            topics__in=lesson_topics
        ).distinct()[:2]
        
        for practice in practice_lessons:
            recommendations.append({
                'title': practice.title,
                'type': 'interactive',
                'difficulty': practice.difficulty,
                'reason': "Practice what you've learned with interactive exercises",
                'link': f"/content/lesson/{practice.id}/"
            })
    
    return recommendations[:3]  # Return top 3 recommendations
    """
