"""from django.db import models
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
    """ 

from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone
from django.core.validators import RegexValidator
from django.conf import settings
from datetime import timedelta

class StudentManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, student_id, password, **extra_fields):
        if not student_id:
            raise ValueError('The Student ID must be set')
        user = self.model(student_id=student_id, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, student_id, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(student_id, password, **extra_fields)

    def create_superuser(self, student_id, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(student_id, password, **extra_fields)

class Student(AbstractUser):
    # Remove the username field
    username = None
    
    # Student ID as the primary key (must be 8 digits)
    student_id = models.CharField(
        max_length=8,
        unique=True,
        primary_key=True,
        validators=[RegexValidator(r'^\d{8}$', 'Student ID must be exactly 8 digits.')],
        error_messages={
            'unique': "A student with this ID already exists.",
        }
    )
    
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
    
    # Set student_id as the username field for authentication
    USERNAME_FIELD = 'student_id'
    REQUIRED_FIELDS = ['email', 'first_name', 'last_name']
    
    # Use our custom manager
    objects = StudentManager()
    
    def __str__(self):
        return self.student_id

class LoginAttempt(models.Model):
    # Store student_id for login attempts
    student_id = models.CharField(max_length=8)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    last_attempt = models.DateTimeField(auto_now=True)

    LOCKOUT_TIME = getattr(settings, "LOCKOUT_TIME", 300)  # default 5 minutes

    @classmethod
    def record_failed_attempt(cls, student_id, ip_address):
        obj, created = cls.objects.get_or_create(
            student_id=student_id,
            defaults={"ip_address": ip_address}
        )
        obj.attempts += 1
        obj.last_attempt = timezone.now()
        obj.save()
        return obj

    @classmethod
    def reset_attempts(cls, student_id):
        cls.objects.filter(student_id=student_id).delete()

    @classmethod
    def is_locked(cls, student_id):
        obj = cls.objects.filter(student_id=student_id).first()
        if not obj:
            return False
        if obj.attempts >= getattr(settings, "MAX_LOGIN_ATTEMPTS", 3):
            if timezone.now() - obj.last_attempt < timedelta(seconds=cls.LOCKOUT_TIME):
                return True
            else:
                # Reset after lockout time
                cls.reset_attempts(student_id)
        return False