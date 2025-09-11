from django.utils import timezone
from datetime import timedelta
from collections import defaultdict
import numpy as np
from engine.models import StudentProfile

class AITrackingSystem:
    def __init__(self):
        self.engagement_data = defaultdict(lambda: defaultdict(list))
    
    def record_engagement(self, student, content_type, content_id, time_spent, interactions):
        """Record student engagement with content"""
        timestamp = timezone.now()
        
        self.engagement_data[student.id][content_type].append({
            'content_id': content_id,
            'timestamp': timestamp,
            'time_spent': time_spent,
            'interactions': interactions
        })
        
        # Update learning patterns periodically
        if len(self.engagement_data[student.id][content_type]) % 5 == 0:  # Every 5 interactions
            self.update_learning_patterns(student)
    
    def update_learning_patterns(self, student):
        """Update learning patterns based on engagement data"""
        profile = StudentProfile.objects.get(student=student)
        engagement = self.engagement_data[student.id]
        
        patterns = {
            'preferred_content_types': {},
            'time_of_day_preference': {},
            'session_lengths': [],
            'engagement_rate': 0
        }
        
        # Analyze content type preferences
        for content_type, sessions in engagement.items():
            patterns['preferred_content_types'][content_type] = len(sessions)
        
        # Analyze time of day preferences
        for content_type, sessions in engagement.items():
            for session in sessions:
                hour = session['timestamp'].hour
                patterns['time_of_day_preference'][hour] = patterns['time_of_day_preference'].get(hour, 0) + 1
        
        # Calculate average session length
        total_time = sum(session['time_spent'] for sessions in engagement.values() for session in sessions)
        total_sessions = sum(len(sessions) for sessions in engagement.values())
        
        if total_sessions > 0:
            patterns['average_session_length'] = total_time / total_sessions
            patterns['engagement_rate'] = total_sessions / (timezone.now() - student.date_joined).days if (timezone.now() - student.date_joined).days > 0 else total_sessions
        
        profile.learning_patterns = patterns
        profile.save()
        
        return patterns
    
    def predict_performance(self, student, upcoming_content):
        """Predict student performance on upcoming content"""
        profile = StudentProfile.objects.get(student=student)
        patterns = profile.learning_patterns or {}
        
        predictions = {}
        
        for content in upcoming_content:
            # Base prediction on content type preference
            content_type_pref = patterns.get('preferred_content_types', {}).get(content.content_type, 0.5)
            
            # Adjust based on mastery level
            mastery_factor = 0.5
            if profile.mastery_level == 'beginner':
                mastery_factor = 0.3
            elif profile.mastery_level == 'intermediate':
                mastery_factor = 0.6
            elif profile.mastery_level == 'advanced':
                mastery_factor = 0.8
            
            # Calculate predicted score (0-100)
            predicted_score = min(100, (content_type_pref + mastery_factor) * 50)
            
            predictions[content.id] = {
                'predicted_score': predicted_score,
                'confidence': 0.7,  # Could be calculated based on data availability
                'recommended_prep': self.generate_prep_recommendations(student, content)
            }
        
        return predictions
    
    def generate_prep_recommendations(self, student, content):
        """Generate preparation recommendations for specific content"""
        profile = StudentProfile.objects.get(student=student)
        
        recommendations = []
        
        # Check if content topics match knowledge gaps
        content_topics = content.topics.split(',') if content.topics else []
        knowledge_gap_topics = [gap['topic'] for gap in profile.knowledge_gaps]
        
        overlapping_gaps = set(content_topics) & set(knowledge_gap_topics)
        
        if overlapping_gaps:
            recommendations.append(f"Review basics of {', '.join(overlapping_gaps)} before starting")
        
        # Recommend based on content type
        if content.content_type == 'video' and 'video' not in profile.learning_patterns.get('preferred_content_types', {}):
            recommendations.append("Consider taking notes while watching the video")
        
        elif content.content_type == 'text' and 'text' not in profile.learning_patterns.get('preferred_content_types', {}):
            recommendations.append("Read actively and summarize key points after each section")
        
        return recommendations

# Initialize AI tracking system
ai_tracker = AITrackingSystem()