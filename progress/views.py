# Create your views here.
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from .models import StudentProgress, LearningGoal
from content.models import Module, Lesson, Exercise
from django.contrib.auth import get_user_model

User = get_user_model()

@login_required
def progress_dashboard(request):
    student = request.user
    progress_data = StudentProgress.objects.filter(student=student)
    
    # Calculate overall progress
    total_modules = Module.objects.count()
    completed_modules = progress_data.filter(status='completed').count()
    overall_progress = (completed_modules / total_modules * 100) if total_modules > 0 else 0
    
    # Get recent activity
    recent_activity = progress_data.order_by('-last_accessed')[:10]
    
    # Get learning goals
    goals = LearningGoal.objects.filter(student=student)
    
    context = {
        'overall_progress': overall_progress,
        'completed_modules': completed_modules,
        'total_modules': total_modules,
        'recent_activity': recent_activity,
        'goals': goals,
    }
    return render(request, 'progress/dashboard.html', context)

@login_required
def update_progress(request, module_id, lesson_id=None, exercise_id=None):
    if request.method == 'POST':
        student = request.user
        module = get_object_or_404(Module, id=module_id)
        lesson = get_object_or_404(Lesson, id=lesson_id) if lesson_id else None
        exercise = get_object_or_404(Exercise, id=exercise_id) if exercise_id else None
        
        status = request.POST.get('status', 'in_progress')
        score = float(request.POST.get('score', 0))
        time_spent = request.POST.get('time_spent')
        
        progress, created = StudentProgress.objects.get_or_create(
            student=student,
            module=module,
            lesson=lesson,
            exercise=exercise,
            defaults={'status': status, 'score': score}
        )
        
        if not created:
            progress.status = status
            progress.score = score
            if time_spent:
                progress.time_spent = time_spent
            progress.attempts += 1
            if status == 'completed':
                progress.completed_at = timezone.now()
            progress.save()
        
        return JsonResponse({'success': True, 'progress_id': progress.id})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def module_progress_detail(request, module_id):
    student = request.user
    module = get_object_or_404(Module, id=module_id)
    
    progress_data = StudentProgress.objects.filter(
        student=student, 
        module=module
    ).select_related('lesson', 'exercise')
    
    context = {
        'module': module,
        'progress_data': progress_data,
    }
    return render(request, 'progress/module_detail.html', context)

@login_required
def set_learning_goal(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        module_id = request.POST.get('module_id')
        target_date = request.POST.get('target_date')
        
        module = get_object_or_404(Module, id=module_id) if module_id else None
        
        goal = LearningGoal.objects.create(
            student=request.user,
            title=title,
            description=description,
            target_module=module,
            target_date=target_date if target_date else None
        )
        
        return JsonResponse({'success': True, 'goal_id': goal.id})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})