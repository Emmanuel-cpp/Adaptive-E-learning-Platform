from django.db import models
from django.utils import timezone

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