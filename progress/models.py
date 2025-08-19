from django.db import models
from django.utils import timezone
from users.models import Student
from content.models import Lesson, Module

class UserProgress(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    is_completed = models.BooleanField(default=False)
    time_spent = models.PositiveIntegerField(default=0)  # Seconds
    last_accessed = models.DateTimeField(default=timezone.now)
    score = models.FloatField(default=0)  # Quiz score 0-100
    
    class Meta:
        unique_together = ('student', 'lesson')
    
    def __str__(self):
        return f"{self.student.username} - {self.lesson.title}"

class ModuleProgress(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    completion_percentage = models.FloatField(default=0)
    
    class Meta:
        unique_together = ('student', 'module')
    
    def __str__(self):
        return f"{self.student.username} - {self.module.title}"