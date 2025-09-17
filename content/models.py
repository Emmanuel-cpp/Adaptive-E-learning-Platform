from django.db import models
from django.utils import timezone
from users.models import Student # Correct import for your Student model
from django.conf import settings

class Course(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return self.title

class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.course.title}: {self.title}"

class Lesson(models.Model):
    CONTENT_TYPES = (
        ('text', 'Text'),
        ('video', 'Video'),
        ('exercise', 'Exercise'),
        ('example', 'Code Example'),
    )
    
    DIFFICULTY_LEVELS = (
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    )
    
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=200)
    content = models.TextField()
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPES, default='text')
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_LEVELS, default='beginner')
    order = models.PositiveIntegerField(default=0)
    estimated_time = models.PositiveIntegerField(default=10, help_text="Minutes required")
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return self.title
    
    
# content/models.py
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class GeneratedCourse(models.Model):
    DIFFICULTY_LEVELS = [
        ('beginner', 'Beginner'),
        ('moderate', 'Moderate'),
        ('advanced', 'Advanced'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=100)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_LEVELS)
    include_video = models.BooleanField(default=False)
    chapters_count = models.IntegerField()
    generated_content = models.JSONField()  # Stores the AI-generated content
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.title

class GeneratedChapter(models.Model):
    course = models.ForeignKey(GeneratedCourse, on_delete=models.CASCADE, related_name='chapters')
    title = models.CharField(max_length=200)
    duration = models.CharField(max_length=50)
    image_prompt = models.TextField()
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return self.title

# In your models.py
class GeneratedTopic(models.Model):
    DIFFICULTY_LEVELS = [
        ('basic', 'Basic'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]
    
    chapter = models.ForeignKey(GeneratedChapter, on_delete=models.CASCADE, related_name='topics')
    title = models.CharField(max_length=200)
    content = models.TextField(default='')
    alternative_content = models.TextField(blank=True, null=True)  # For simplified content
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_LEVELS, default='intermediate')
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    is_regenerated = models.BooleanField(default=False)
    original_topic = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='regenerated_versions')
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return self.title
    
    
class GeneratedQuiz(models.Model):
    """
    Model to hold a quiz generated for a specific topic.
    """
    topic = models.OneToOneField(GeneratedTopic, on_delete=models.CASCADE, related_name='quiz')
    
    def __str__(self):
        return f"Quiz for {self.topic.title}"

class GeneratedQuestion(models.Model):
    """
    Model to hold a single question within a quiz.
    """
    quiz = models.ForeignKey(GeneratedQuiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.question_text[:50] + "..." if len(self.question_text) > 50 else self.question_text

class GeneratedAnswer(models.Model):
    """
    Model to hold a single answer option for a question.
    """
    question = models.ForeignKey(GeneratedQuestion, on_delete=models.CASCADE, related_name='answers')
    answer_text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)
    option_key = models.CharField(max_length=1, default='A')  # e.g., A, B, C, D
    order = models.IntegerField(default=0)  

    def __str__(self):
        return f"{self.option_key}: {self.answer_text}"   
"""
# New model to track generated course progress
class GeneratedCourseProgress(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='generated_course_progresses')
    course = models.ForeignKey(GeneratedCourse, on_delete=models.CASCADE, related_name='progresses')
    last_accessed_topic = models.ForeignKey('GeneratedTopic', on_delete=models.SET_NULL, null=True, related_name='+', help_text="The last topic the user viewed.")
    last_accessed_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Progress for {self.student.username} on {self.course.title}"
"""        

# New model to track completed topics
class CompletedTopic(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='completed_topics')
    topic = models.ForeignKey('GeneratedTopic', on_delete=models.CASCADE, related_name='completed_by')
    completed_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.student.username} completed {self.topic.title}"   
    
class GeneratedCourseProgress(models.Model):
    """
    Tracks the last accessed topic for a generated course.
    """
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='generated_course_progresses')
    course = models.ForeignKey(GeneratedCourse, on_delete=models.CASCADE, related_name='progresses')
    last_accessed_topic = models.ForeignKey(GeneratedTopic, on_delete=models.SET_NULL, null=True, blank=True)
    last_accessed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Generated Course Progresses"
        unique_together = ('student', 'course')
    
    def __str__(self):
        return f"{self.student.username}'s progress on {self.course.title}"

class GeneratedTopicCompletion(models.Model):
    """
    Tracks which topics have been marked as complete by a student.
    """
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    topic = models.ForeignKey(GeneratedTopic, on_delete=models.CASCADE)
    completed_at = models.DateTimeField(auto_now_add=True)
    score = models.FloatField(null=True, blank=True) 
    passed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('student', 'topic')
        
    def __str__(self):
        return f"{self.student.username} completed {self.topic.title}"      
    
    
class CppLearningResource(models.Model):
    RESOURCE_TYPES = [
        ('video', 'Video'),
        ('article', 'Article'),
        ('tutorial', 'Interactive Tutorial'),
        ('exercise', 'Practice Exercises'),
        ('documentation', 'Official Documentation'),
    ]
    
    TOPIC_CATEGORIES = [
        ('syntax', 'Syntax Basics'),
        ('oop', 'Object-Oriented Programming'),
        ('stl', 'STL & Templates'),
        ('memory', 'Memory Management'),
        ('advanced', 'Advanced Concepts'),
    ]
    
    title = models.CharField(max_length=200)
    url = models.URLField()
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPES)
    topic_category = models.CharField(max_length=20, choices=TOPIC_CATEGORIES)
    difficulty = models.CharField(max_length=20, choices=GeneratedTopic.DIFFICULTY_LEVELS)
    description = models.TextField()
    source = models.CharField(max_length=100)  # e.g., 'freeCodeCamp', 'W3Schools'
    
    def __str__(self):
        return f"{self.title} ({self.source})"    