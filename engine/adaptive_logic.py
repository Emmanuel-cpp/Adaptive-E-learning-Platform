from django.db.models import Q
from content.models import Lesson, Module
from progress.models import UserProgress

def get_next_lesson(student, current_lesson=None):
    if not current_lesson:
        # Start with first lesson in first module of first course
        return Lesson.objects.order_by('module__course__order', 'module__order', 'order').first()

    current_course = current_lesson.module.course
    current_module = current_lesson.module

    # 1. First try to get next lesson in same module
    next_in_module = Lesson.objects.filter(
        module=current_module,
        order__gt=current_lesson.order
    ).order_by('order').first()
    
    if next_in_module:
        return next_in_module

    # 2. Try to get first lesson in next module (same course)
    next_module = Module.objects.filter(
        course=current_course,
        order__gt=current_module.order
    ).order_by('order').first()

    if next_module:
        return next_module.lessons.order_by('order').first()

    # 3. If no next module, check for adaptive recommendations
    # But only if we're not at the last lesson
    adaptive_lesson = get_adaptive_lesson(student, current_lesson)
    if adaptive_lesson:
        return adaptive_lesson

    # 4. Final fallback: next lesson in course sequence
    return Lesson.objects.filter(
        module__course=current_course,
        module__order__gte=current_module.order,
        order__gt=current_lesson.order
    ).order_by('module__order', 'order').first()

def get_adaptive_lesson(student, current_lesson):
    """Get adaptive lesson recommendation if applicable"""
    # Check if struggling with current concept
    try:
        progress = UserProgress.objects.get(
            student=student, 
            lesson=current_lesson
        )
        if progress.score < 60:  # Below passing threshold
            remedial = get_remedial_lesson(current_lesson)
            if remedial:
                return remedial
    except UserProgress.DoesNotExist:
        pass

    # Handle learning style alternatives within current module
    if student.learning_style == 'visual':
        visual = get_visual_alternative(current_lesson)
        if visual:
            return visual
    elif student.learning_style == 'kinesthetic':
        practice = get_practice_lesson(current_lesson)
        if practice:
            return practice
            
    return None

def get_remedial_lesson(lesson):
    # Find easier version in same module
    return Lesson.objects.filter(
        module=lesson.module,
        difficulty='beginner'
    ).exclude(id=lesson.id).order_by('order').first()

def get_visual_alternative(lesson):
    # Find video explanation in same module
    return Lesson.objects.filter(
        module=lesson.module,
        content_type='video'
    ).exclude(id=lesson.id).order_by('order').first()

def get_practice_lesson(lesson):
    # Find coding exercise in same module
    return Lesson.objects.filter(
        module=lesson.module,
        content_type='exercise'
    ).exclude(id=lesson.id).order_by('order').first()

def get_previous_lesson(current_lesson):
    # Previous lesson in same module
    prev_in_module = Lesson.objects.filter(
        module=current_lesson.module,
        order__lt=current_lesson.order
    ).order_by('-order').first()
    
    if prev_in_module:
        return prev_in_module
    
    # Previous module's last lesson
    prev_module = Module.objects.filter(
        course=current_lesson.module.course,
        order__lt=current_lesson.module.order
    ).order_by('-order').first()
    
    if prev_module:
        return prev_module.lessons.order_by('-order').first()
    
    return None