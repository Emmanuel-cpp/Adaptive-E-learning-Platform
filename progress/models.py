
# Create your models here.
from django.db import models
from django.contrib.auth import get_user_model
from content.models import Course, Module, Lesson

User = get_user_model()

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from content.models import Lesson, GeneratedTopic  # Import GeneratedTopic

User = get_user_model()

class UserProgress(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='progress')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, null=True, blank=True, related_name='progress')
    generated_topic = models.ForeignKey(GeneratedTopic, on_delete=models.CASCADE, null=True, blank=True, related_name='progress') # ADD THIS LINE
    is_completed = models.BooleanField(default=False)
    score = models.IntegerField(null=True, blank=True)
    last_accessed = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_spent = models.DurationField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    
    class Meta:
        verbose_name_plural = "User Progress"
        unique_together = ('student', 'lesson', 'generated_topic') # ENSURE THIS IS A TUPLE

    def __str__(self):
        if self.lesson:
            return f"{self.student.username} - {self.lesson.title}"
        elif self.generated_topic:
            return f"{self.student.username} - {self.generated_topic.title}"
        return f"{self.student.username} - Progress"

    def save(self, *args, **kwargs):
        if self.is_completed and not self.completed_at:
            self.completed_at = timezone.now()
        super().save(*args, **kwargs)

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
        