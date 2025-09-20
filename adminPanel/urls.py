# adminPanel/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.admin_login_view, name='admin_login'),
    path('adminDashboard/', views.admin_dashboard, name='Admindashboard'),
    path('admin/student-details/<int:student_id>/', views.student_details, name='student_details'),
    path('admin/performance-distribution/', views.performance_distribution, name='performance_distribution'),
    path('admin/learning-style-distribution/', views.learning_style_distribution, name='learning_style_distribution'),
    path('admin/completion-over-time/', views.completion_over_time, name='completion_over_time'),
    path('admin/quiz-performance/', views.quiz_performance, name='quiz_performance'),
    path('admin/top-performers/', views.top_performers, name='top_performers'),
    path('admin/student-quizzes/<int:student_id>/', views.student_quizzes, name='student_quizzes'),
    path('admin/student-progress/<int:student_id>/', views.student_progress_details, name='student_progress_details'),

]