# content/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('learning/<int:lesson_id>/', views.learning_view, name='learning'),
    path('learning/', views.learning_view, name='learning_default'),
    path('complete-lesson/<int:lesson_id>/', views.complete_lesson, name='complete_lesson'),
    path('update-lesson-time/<int:lesson_id>/', views.update_lesson_time, name='update_lesson_time'),
    path('course/<int:course_id>/', views.course_detail, name='course_detail'),
    path('api/generate-course/', views.generate_course, name='generate_course'),
    path('complete-lesson/<int:lesson_id>/', views.complete_lesson, name='complete_lesson'),
    path('api/complete-generated-topic/<int:topic_id>/', views.complete_generated_topic, name='complete_generated_topic'),
    path('api/complete-generated-topic/', views.complete_generated_topic, name='complete_generated_topic'),
    path('learning/', views.learning_default, name='learning_default'),
    path('api/complete_topic/', views.complete_topic, name='complete_topic'),
    path('api/get-topic-data/<int:topic_id>/', views.get_topic_data_api, name='get_topic_data_api'),
    path('progress-analysis/', views.progress_analysis_view, name='progress_analysis'),
]