from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class Student(AbstractUser):
    LEARNING_STYLES = [
        ('visual', 'Visual Learner'),
        ('auditory', 'Auditory Learner'),
        ('kinesthetic', 'Kinesthetic Learner'),
    ]
    
    MASTERY_LEVELS = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]
    
    learning_style = models.CharField(
        max_length=20, 
        choices=LEARNING_STYLES, 
        default='visual'
    )
    mastery_level = models.CharField(
        max_length=20, 
        choices=MASTERY_LEVELS, 
        default='beginner'
    )
    profile_picture = models.ImageField(
        upload_to='profiles/', 
        null=True, 
        blank=True
    )
    last_active = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return self.username