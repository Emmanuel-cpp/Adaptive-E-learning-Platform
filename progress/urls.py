from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.progress_dashboard, name='progress_dashboard'),
    path('module/<int:module_id>/', views.module_progress_detail, name='module_progress'),
    path('update/<int:module_id>/', views.update_progress, name='update_progress'),
    path('update/<int:module_id>/<int:lesson_id>/', views.update_progress, name='update_lesson_progress'),
    path('update/<int:module_id>/<int:lesson_id>/<int:exercise_id>/', views.update_progress, name='update_exercise_progress'),
    path('set-goal/', views.set_learning_goal, name='set_learning_goal'),
]