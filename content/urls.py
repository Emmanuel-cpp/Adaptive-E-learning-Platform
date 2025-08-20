from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('learning/', views.learning_view, name='learning_default'),
    path('learning/<int:lesson_id>/', views.learning_view, name='learning'),
    path('complete/<int:lesson_id>/', views.mark_lesson_completed, name='complete_lesson'),
    path('course/<int:course_id>/', views.course_detail, name='course_detail'),
]