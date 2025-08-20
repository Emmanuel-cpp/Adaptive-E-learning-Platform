from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from django.conf import settings


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
    

class LoginAttempt(models.Model):
    username = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    last_attempt = models.DateTimeField(auto_now=True)

    LOCKOUT_TIME = getattr(settings, "LOCKOUT_TIME", 300)  # default 5 minutes

    @classmethod
    def record_failed_attempt(cls, username, ip_address):
        obj, created = cls.objects.get_or_create(username=username, defaults={"ip_address": ip_address})
        obj.attempts += 1
        obj.last_attempt = timezone.now()
        obj.save()
        return obj

    @classmethod
    def reset_attempts(cls, username):
        cls.objects.filter(username=username).delete()

    @classmethod
    def is_locked(cls, username):
        obj = cls.objects.filter(username=username).first()
        if not obj:
            return False
        if obj.attempts >= getattr(settings, "MAX_LOGIN_ATTEMPTS", 3):
            if timezone.now() - obj.last_attempt < timedelta(seconds=cls.LOCKOUT_TIME):
                return True
            else:
                # Reset after lockout time
                cls.reset_attempts(username)
        return False
    
    