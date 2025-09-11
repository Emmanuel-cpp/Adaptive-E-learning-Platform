from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages
from django.http import JsonResponse
from .models import Course, Module, Lesson
from progress.models import UserProgress,ModuleProgress
from engine.adaptive_learning import get_next_lesson, get_previous_lesson
from django.utils import timezone
import datetime
from users.decorators import prevent_after_logout
from engine.adaptive_learning import ai_engine


@prevent_after_logout
@login_required
def dashboard_view(request):
    student = request.user
    courses = Course.objects.all()
    
    # Get progress data
    progress_data = []
    for course in courses:
        completed_lessons = 0
        total_lessons = 0
        
        for module in course.modules.all():
            total_lessons += module.lessons.count()
            completed_lessons += UserProgress.objects.filter(
                student=student,
                lesson__module=module,
                is_completed=True
            ).count()
        
        progress_percentage = int((completed_lessons / total_lessons) * 100) if total_lessons > 0 else 0
        
        # Get recent activity for this course
        recent_activity = UserProgress.objects.filter(
            student=student,
            lesson__module__course=course
        ).order_by('-last_accessed')[:3]
        
        progress_data.append({
            'course': course,
            'progress': progress_percentage,
            'completed_lessons': completed_lessons,
            'total_lessons': total_lessons,
            'recent_activity': recent_activity
        })
    
    # Get overall statistics
    total_completed = UserProgress.objects.filter(student=student, is_completed=True).count()
    total_lessons = Lesson.objects.count()
    overall_progress = int((total_completed / total_lessons) * 100) if total_lessons > 0 else 0
    
    # Get recent activity across all courses
    recent_activity = UserProgress.objects.filter(
        student=student
    ).select_related('lesson', 'lesson__module', 'lesson__module__course').order_by('-last_accessed')[:5]
    
    return render(request, 'dashboard.html', {
        'progress_data': progress_data,
        'student': student,
        'overall_progress': overall_progress,
        'total_completed': total_completed,
        'total_lessons': total_lessons,
        'recent_activity': recent_activity
    })

@prevent_after_logout
@login_required
def learning_view(request, lesson_id=None):
    student = request.user
    
    # Get current lesson
    if lesson_id:
        lesson = get_object_or_404(Lesson, id=lesson_id)
    else:
        # Start with first incomplete lesson or first lesson overall
        incomplete_lessons = Lesson.objects.exclude(
            userprogress__student=student,
            userprogress__is_completed=True
        ).order_by('module__order', 'order')
        
        lesson = incomplete_lessons.first()
        
        if not lesson:
            # All lessons completed - start from first lesson
            lesson = Lesson.objects.order_by('module__order', 'order').first()
        
        if lesson:
            return redirect('learning', lesson_id=lesson.id)
        else:
            
            return redirect('dashboard')
    
    # Update progress
    progress, created = UserProgress.objects.get_or_create(
        student=student,
        lesson=lesson,
        defaults={'last_accessed': timezone.now()}
    )
    
    if not created:
        progress.last_accessed = timezone.now()
        progress.save()
    
    # Get module progress
    module = lesson.module
    completed_lessons = UserProgress.objects.filter(
        student=student,
        lesson__module=module,
        is_completed=True
    ).count()
    total_lessons = module.lessons.count()
    progress_percentage = int((completed_lessons / total_lessons) * 100) if total_lessons else 0
    
    # Get next and previous lessons
    next_lesson = get_next_lesson(student, lesson)
    previous_lesson = get_previous_lesson(student, lesson)
    
    # Ensure next_lesson is not the current lesson
    if next_lesson and next_lesson.id == lesson.id:
        next_lesson = None
    
    # Get AI recommendations for this lesson
    #ai_recommendations = ai_engine.get_lesson_recommendations(student, lesson)
    
    # Get completed modules and lessons
    completed_modules = Module.objects.filter(
        lessons__userprogress__student=student,
        lessons__userprogress__is_completed=True
    ).distinct()
    
    completed_lessons = Lesson.objects.filter(
        userprogress__student=student,
        userprogress__is_completed=True
    )
    
    return render(request, 'learning.html', {
        'course': module.course,
        'module': module,
        'lesson': lesson,
        'progress_percentage': progress_percentage,
        'next_lesson': next_lesson,
        'previous_lesson': previous_lesson,
        #'ai_recommendations': ai_recommendations,
        'completed_modules': completed_modules,
        'completed_lessons': completed_lessons
    })
    
@login_required
def complete_lesson(request, lesson_id):
    """Mark a lesson as completed"""
    if request.method == 'POST':
        lesson = get_object_or_404(Lesson, id=lesson_id)
        student = request.user
        
        # Update or create progress record
        progress, created = UserProgress.objects.update_or_create(
            student=student,
            lesson=lesson,
            defaults={
                'is_completed': True,
                'completed_at': timezone.now(),
                'score': request.POST.get('score', 100),
                'last_accessed': timezone.now()
            }
        )
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'progress_id': progress.id})
        
        #messages.success(request, f"Lesson '{lesson.title}' marked as completed!")
        return redirect('learning', lesson_id=lesson_id)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@login_required
def update_lesson_time(request, lesson_id):
    """Update time spent on a lesson"""
    if request.method == 'POST':
        lesson = get_object_or_404(Lesson, id=lesson_id)
        student = request.user
        time_spent = request.POST.get('time_spent')
        
        if time_spent:
            progress, created = UserProgress.objects.get_or_create(
                student=student,
                lesson=lesson,
                defaults={'last_accessed': timezone.now()}
            )
            
            if not created:
                progress.last_accessed = timezone.now()
                # You might want to add time tracking logic here
                progress.save()
            
            return JsonResponse({'success': True})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
def course_detail(request, course_id):
    """Detailed view of a course with module progress"""
    course = get_object_or_404(Course, id=course_id)
    student = request.user
    
    module_progress = []
    for module in course.modules.all():
        completed_lessons = UserProgress.objects.filter(
            student=student,
            lesson__module=module,
            is_completed=True
        ).count()
        total_lessons = module.lessons.count()
        progress_percentage = int((completed_lessons / total_lessons) * 100) if total_lessons > 0 else 0
        
        module_progress.append({
            'module': module,
            'completed_lessons': completed_lessons,
            'total_lessons': total_lessons,
            'progress_percentage': progress_percentage
        })
    
    return render(request, 'content/course_detail.html', {
        'course': course,
        'module_progress': module_progress,
        'student': student
    })