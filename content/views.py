from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Course, Module, Lesson
from progress.models import UserProgress, ModuleProgress
from engine.adaptive_logic import get_next_lesson, get_previous_lesson
from django.contrib import messages

@login_required
def dashboard_view(request):
    student = request.user
    courses = Course.objects.all()
    
    # Get progress data
    progress_data = []
    for course in courses:
        completed = 0
        total = 0
        
        for module in course.modules.all():
            total += module.lessons.count()
            completed += UserProgress.objects.filter(
                student=student,
                lesson__module=module,
                is_completed=True
            ).count()
        
        progress_data.append({
            'course': course,
            'progress': int((completed / total) * 100) if total > 0 else 0
        })
    
    return render(request, 'dashboard.html', {
        'progress_data': progress_data,
        'student': student
    })

@login_required
def learning_view(request, lesson_id=None):
    student = request.user
    
    # Get current lesson - FIXED: Proper initial lesson selection
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
            messages.info(request, "No lessons available yet")
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
    
    # Get recommendations - FIXED: Ensure next_lesson is not current lesson
    next_lesson = get_next_lesson(student, lesson)
    if next_lesson and next_lesson.id == lesson.id:
        next_lesson = None  # Prevent infinite loop
    
    previous_lesson = get_previous_lesson(lesson)
    
    return render(request, 'learning.html', {
        'course': module.course,
        'module': module,
        'lesson': lesson,
        'progress_percentage': progress_percentage,
        'next_lesson': next_lesson,
        'previous_lesson': previous_lesson
    })