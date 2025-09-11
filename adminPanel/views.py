# users/views.py - Add this to your existing views
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import timedelta
from progress.models import CourseProgress, ModuleProgress, UserProgress
from content.models import Course, Module, Lesson
from django.db.models import Avg, Count, Sum
from django.contrib.auth import get_user_model
# Add these imports at the top of your views.py file
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Avg, Sum, Q, Max
from django.db.models.functions import Greatest
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.shortcuts import render
from content.models import Course, Module, Lesson
from progress.models import CourseProgress, ModuleProgress, UserProgress
from django.db.models.functions import Coalesce

User = get_user_model()

@staff_member_required
def admin_dashboard(request):
    # Get current time and time ranges for analytics
    now = timezone.now()
    one_week_ago = now - timedelta(days=7)
    one_day_ago = now - timedelta(days=1)
    
    # User statistics
    User = get_user_model()
    total_students = User.objects.filter(is_staff=False).count()
    new_students_this_week = User.objects.filter(
        is_staff=False, 
        date_joined__gte=one_week_ago
    ).count()
    
    # Course statistics
    course = Course.objects.first()  # Assuming one course for now
    total_modules = Module.objects.count()
    total_lessons = Lesson.objects.count()
    
    # Progress statistics
    avg_progress = CourseProgress.objects.aggregate(
        avg_progress=Avg('completion_percentage')
    )['avg_progress'] or 0
    
    # Calculate progress change from last week
    progress_last_week = CourseProgress.objects.filter(
        last_accessed__gte=one_week_ago,
        last_accessed__lt=one_day_ago
    ).aggregate(avg_progress=Avg('completion_percentage'))['avg_progress'] or 0
    
    progress_change = round(avg_progress - progress_last_week, 1) if progress_last_week else 0
    
    # Active users (accessed progress in last 30 minutes)
    active_now = User.objects.filter(
        Q(lesson_progress__last_accessed__gte=now-timedelta(minutes=30)) |
        Q(module_progress__last_accessed__gte=now-timedelta(minutes=30)) |
        Q(course_progress__last_accessed__gte=now-timedelta(minutes=30))
    ).distinct().count()
    
    # Active users yesterday at same time
    active_yesterday = User.objects.filter(
        Q(lesson_progress__last_accessed__gte=now-timedelta(days=1, minutes=30)) &
        Q(lesson_progress__last_accessed__lt=now-timedelta(days=1)) |
        Q(module_progress__last_accessed__gte=now-timedelta(days=1, minutes=30)) &
        Q(module_progress__last_accessed__lt=now-timedelta(days=1)) |
        Q(course_progress__last_accessed__gte=now-timedelta(days=1, minutes=30)) &
        Q(course_progress__last_accessed__lt=now-timedelta(days=1))
    ).distinct().count()
    
    active_change = active_now - active_yesterday
    
    # Use the correct field name 'lessons' (plural)
    modules = Module.objects.annotate(
        lesson_count=Count('lessons'),
        total_duration=Sum('lessons__estimated_time')
    )
    """
    # Student progress data - use a different name for the annotation to avoid conflict
    student_progress = User.objects.filter(is_staff=False).annotate(
        progress_percentage=Avg('course_progress__completion_percentage'),
        last_activity=Greatest(  # Changed from last_active to last_activity
            Max('lesson_progress__last_accessed'),
            Max('module_progress__last_accessed'),
            Max('course_progress__last_accessed')
        )
    ).order_by('-last_activity')[:10]  # Top 10 most recent"""
    # In your admin_dashboard view, replace the student_progress query:
    student_progress = User.objects.filter(is_staff=False).annotate(
        progress_percentage=Coalesce(Avg('course_progress__completion_percentage'), 0.0),
        last_activity=Greatest(
            Max('lesson_progress__last_accessed'),
            Max('module_progress__last_accessed'),
            Max('course_progress__last_accessed')
        )
    ).order_by('-last_activity')[:10]
    
    # Add this to your view after calculating student_progress
    now = timezone.now()
    for student in student_progress:
        student.is_active = student.last_activity and (now - student.last_activity) < timedelta(minutes=30)
            
    context = {
        'total_students': total_students,
        'new_students_this_week': new_students_this_week,
        'avg_progress': round(avg_progress, 1),
        'progress_change': progress_change,
        'active_now': active_now,
        'active_change': active_change,
        'modules': modules,
        'student_progress': student_progress,
    }
    
    return render(request, 'admin_dashboard.html', context)

from django.conf import settings
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login
from users.models import LoginAttempt
@csrf_exempt
def admin_login_view(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('admin_dashboard')
        else:
            messages.warning(request, 'You are not authorized to access the admin panel.')
            return redirect('dashboard')
            
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Check if account is locked
        if LoginAttempt.is_locked(username):
            messages.error(request, 'Account temporarily locked due to too many failed login attempts.')
            return render(request, 'admin_login.html')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if user.is_staff:  # Only allow staff users
                LoginAttempt.reset_attempts(username)
                login(request, user)
                request.session.set_expiry(0)
                return redirect('admin_dashboard')
            else:
                messages.error(request, 'You do not have admin privileges.')
        else:
            # Record failed attempt
            attempt = LoginAttempt.record_failed_attempt(username, request.META.get('REMOTE_ADDR'))
            
            remaining_attempts = settings.MAX_LOGIN_ATTEMPTS - attempt.attempts
            if remaining_attempts > 0:
                messages.error(request, f'Invalid username or password. {remaining_attempts} attempts remaining.')
            else:
                messages.error(request, 'Account temporarily locked due to too many failed login attempts.')
    
    return render(request, 'admin_login.html')
