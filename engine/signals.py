from django.db.models.signals import post_save
from django.dispatch import receiver
from progress.models import ModuleProgress, UserProgress
from engine.adaptive_learning import ai_engine

@receiver(post_save, sender=ModuleProgress)
def update_ai_on_progress(sender, instance, **kwargs):
    """Update AI models when progress is recorded"""
    if instance.completed and instance.score is not None:
        # Convert score to a format the AI expects
        assessment_data = {
            'module': instance.module.id,
            'score': instance.score / 100  # Convert to 0-1 range
        }
        
        # Analyze the results
        ai_engine.analyze_assessment_results(instance.student, assessment_data)