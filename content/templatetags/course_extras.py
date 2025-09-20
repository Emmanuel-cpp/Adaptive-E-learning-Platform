from django import template
from ..models import GeneratedTopicCompletion

register = template.Library()

@register.filter
def topics_completed(topics, user):
    completed_count = 0
    for topic in topics.all():
        try:
            completion = GeneratedTopicCompletion.objects.get(student=user, topic=topic)
            if completion.score >= 50:
                completed_count += 1
        except GeneratedTopicCompletion.DoesNotExist:
            pass
    return completed_count