from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

from engine.adaptive_learning import ai_engine
from engine.content_integration import content_integrator
from engine.ai_tracking import ai_tracker
from engine.models import ContentRecommendation, LearningPath, StudentProfile
from users.models import Student
from content.models import Course, Lesson
from progress.models import ModuleProgress
from content.models import Module

@login_required
def adaptive_dashboard(request):
    """Dashboard with AI-powered recommendations"""
    student = request.user
    course = Course.objects.first()  # Assuming one course for now
    
    # Get AI recommendations
    recommendations = ContentRecommendation.objects.filter(
        student=student,
        completed=False
    ).order_by('-priority')[:5]
    
    # Get learning path
    learning_path = LearningPath.objects.filter(student=student, course=course).first()
    if not learning_path:
        learning_path = ai_engine.generate_learning_path(student, course)
    
    # Get current progress
    progress = ModuleProgress.objects.filter(student=student).aggregate(
        completed=models.Count('id', filter=models.Q(completed=True)),
        total=models.Count('id')
    )
    
    context = {
        'student': student,
        'recommendations': recommendations,
        'learning_path': learning_path,
        'progress': progress,
        'progress_percentage': (progress['completed'] / progress['total'] * 100) if progress['total'] > 0 else 0
    }
    
    return render(request, 'engine/adaptive_dashboard.html', context)

@login_required
def content_recommendations(request):
    """View all content recommendations"""
    student = request.user
    recommendations = ContentRecommendation.objects.filter(student=student).order_by('-priority')
    
    context = {
        'recommendations': recommendations
    }
    
    return render(request, 'engine/content_recommendations.html', context)

@login_required
@csrf_exempt
def record_engagement(request):
    """API endpoint to record student engagement"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            student = request.user
            
            ai_tracker.record_engagement(
                student=student,
                content_type=data.get('content_type'),
                content_id=data.get('content_id'),
                time_spent=data.get('time_spent', 0),
                interactions=data.get('interactions', [])
            )
            
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

@login_required
def learning_insights(request):
    """View AI-generated learning insights"""
    student = request.user
    profile = StudentProfile.objects.get(student=student)
    
    # Get predicted performance for upcoming content
    course = Course.objects.first()
    upcoming_modules = Module.objects.filter(course=course).exclude(
        id__in=ModuleProgress.objects.filter(student=student, completed=True).values('module_id')
    )[:5]
    
    predictions = ai_tracker.predict_performance(student, upcoming_modules)
    
    context = {
        'profile': profile,
        'predictions': predictions,
        'upcoming_modules': upcoming_modules
    }
    
    return render(request, 'engine/learning_insights.html', context)

@login_required
def integrate_external_content(request, topic):
    """Integrate external content for a specific topic"""
    course = Course.objects.first()
    result = content_integrator.fetch_and_integrate_content(topic, course)
    
    if result:
        return JsonResponse({
            'status': 'success',
            'module': result['module'].title,
            'lessons_created': len(result['lessons'])
        })
    else:
        return JsonResponse({'status': 'error', 'message': 'Failed to integrate content'})
    
def get_lesson_recommendations(self, student, lesson):
    """Get AI-powered recommendations for a specific lesson"""
    profile = self.get_or_create_profile(student)
    
    recommendations = []
    
    # Recommend additional resources based on lesson topics
    lesson_topics = lesson.topics.split(',') if lesson.topics else []
    
    for topic in lesson_topics:
        topic = topic.strip()
        if topic:
            # Find related content
            related_content = self.find_content_for_topic(topic, profile.learning_style)
            for content in related_content:
                recommendations.append({
                    'title': f"More about {topic}",
                    'type': content.content_type,
                    'difficulty': content.difficulty,
                    'reason': f"Deepen your understanding of {topic}",
                    'link': f"/content/lesson/{content.id}/"
                })
    
    # Recommend practice exercises
    if lesson.content_type != 'interactive':
        practice_lessons = Lesson.objects.filter(
            module__course=lesson.module.course,
            content_type='interactive',
            topics__in=lesson_topics
        )[:2]
        
        for practice in practice_lessons:
            recommendations.append({
                'title': f"Practice: {practice.title}",
                'type': 'interactive',
                'difficulty': practice.difficulty,
                'reason': "Practice what you've learned with interactive exercises",
                'link': f"/content/lesson/{practice.id}/"
            })
    
    return recommendations[:3]  # Return top 3 recommendations    