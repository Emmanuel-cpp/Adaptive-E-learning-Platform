from django.db import models
from django.utils import timezone
from users.models import Student
from django.conf import settings
from django.core.exceptions import ValidationError

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

class GeneratedCourse(models.Model):
    LEVEL_CHOICES = [
        ('beginner', 'Beginner'),
        ('moderate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=100, default="C++ Programming")
    include_video = models.BooleanField(default=False)
    chapters_count = models.IntegerField(default=0)
    generated_content = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='beginner')
    
    class Meta:
        # Remove the unique constraint that was causing issues
        constraints = []
    
    def __str__(self):
        return self.title

class GeneratedChapter(models.Model):
    course = models.ForeignKey(GeneratedCourse, on_delete=models.CASCADE, related_name='chapters')
    title = models.CharField(max_length=200)
    duration = models.CharField(max_length=50, default="N/A")
    image_prompt = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return self.title

class GeneratedTopic(models.Model):
    DIFFICULTY_LEVELS = [
        ('basic', 'Basic'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]
    
    chapter = models.ForeignKey(GeneratedChapter, on_delete=models.CASCADE, related_name='topics')
    title = models.CharField(max_length=200)
    content = models.TextField(default='')
    alternative_content = models.TextField(blank=True, null=True)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_LEVELS, default='intermediate')
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    is_regenerated = models.BooleanField(default=False)
    is_generated = models.BooleanField(default=True)  # Added default value
    original_topic = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='regenerated_versions')
    is_reinforcement = models.BooleanField(default=False)
    reinforcement_for_chapter = models.ForeignKey(
        'GeneratedChapter', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='reinforcement_topics'
    )
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return self.title

class GeneratedQuiz(models.Model):
    topic = models.OneToOneField(GeneratedTopic, on_delete=models.CASCADE, related_name='quiz')
    
    def __str__(self):
        return f"Quiz for {self.topic.title}"

class GeneratedQuestion(models.Model):
    quiz = models.ForeignKey(GeneratedQuiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    order = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.question_text[:50] + "..." if len(self.question_text) > 50 else self.question_text

class GeneratedAnswer(models.Model):
    question = models.ForeignKey(GeneratedQuestion, on_delete=models.CASCADE, related_name='answers')
    answer_text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)
    option_key = models.CharField(max_length=1, default='A')
    order = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.option_key}: {self.answer_text}"

class GeneratedCourseProgress(models.Model):
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
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    topic = models.ForeignKey(GeneratedTopic, on_delete=models.CASCADE)
    completed_at = models.DateTimeField(auto_now_add=True)
    score = models.FloatField(null=True, blank=True)
    passed = models.BooleanField(default=False)
    wrong_answers = models.JSONField(default=list, blank=True)
    attempt_count = models.PositiveIntegerField(default=1)

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
    source = models.CharField(max_length=100)
    
    def __str__(self):
        return f"{self.title} ({self.source})"