from django.db import models
from users.models import Student
from content.models import Course, Module, Lesson

class StudentProfile(models.Model):
    student = models.OneToOneField(Student, on_delete=models.CASCADE, primary_key=True)
    learning_style = models.CharField(max_length=20, choices=Student.LEARNING_STYLES)
    mastery_level = models.CharField(max_length=20, choices=Student.MASTERY_LEVELS)
    knowledge_gaps = models.JSONField(default=list)  # Stores list of topics with low mastery
    strengths = models.JSONField(default=list)       # Stores list of topics with high mastery
    learning_patterns = models.JSONField(default=dict)  # Stores learning behavior patterns
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AI Profile for {self.student}"

class ContentRecommendation(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    content = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    reason = models.TextField()  # Why this recommendation was made
    priority = models.IntegerField(default=1)  # 1-5, with 5 being highest priority
    created_at = models.DateTimeField(auto_now_add=True)
    viewed = models.BooleanField(default=False)
    completed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-priority', 'created_at']

    def __str__(self):
        return f"Recommendation for {self.student}: {self.content}"

class LearningPath(models.Model):
    student = models.OneToOneField(Student, on_delete=models.CASCADE, primary_key=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    path = models.JSONField(default=list)  # Ordered list of module IDs
    current_position = models.IntegerField(default=0)
    estimated_completion_time = models.DurationField(null=True, blank=True)
    adaptive_adjustments = models.JSONField(default=list)  # History of adjustments made

    def __str__(self):
        return f"Learning Path for {self.student} in {self.course}"