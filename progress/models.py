
# Create your models here.
from django.db import models
from django.contrib.auth import get_user_model
from content.models import Course, Module, Lesson

User = get_user_model()

class UserProgress(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lesson_progress')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    is_completed = models.BooleanField(default=False)
    score = models.FloatField(default=0.0)
    time_spent = models.DurationField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    last_accessed = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['student', 'lesson']
    
    def __str__(self):
        return f"{self.student.username} - {self.lesson.title}"

class ModuleProgress(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='module_progress')
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    is_completed = models.BooleanField(default=False)
    completion_percentage = models.FloatField(default=0.0)
    last_accessed = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['student', 'module']
    
    def __str__(self):
        return f"{self.student.username} - {self.module.title}"

class CourseProgress(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_progress')
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    completion_percentage = models.FloatField(default=0.0)
    last_accessed = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['student', 'course']
     
    def __str__(self):
        return f"{self.student.username} - {self.course.title}"
        