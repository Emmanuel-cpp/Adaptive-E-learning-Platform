from django.contrib import admin
from .models import StudentProfile, ContentRecommendation, LearningPath
# Register your models here.

admin.register(StudentProfile)
admin.register(ContentRecommendation)
admin.register(LearningPath)