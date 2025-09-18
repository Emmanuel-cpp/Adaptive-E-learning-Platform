from django.contrib import admin
from django.urls import path
from users.views import login_view, register_view, logout_view, index_view
from adminPanel.views import admin_login_view
from content.views import dashboard_view, learning_view, complete_lesson, update_lesson_time, course_detail,generate_course, complete_generated_topic, get_topic_data_api, complete_topic, learning_default, progress_analysis_view, regenerate_topic
from adminPanel.views import admin_dashboard
from django.urls import include
from adminPanel.views import delete_student, student_details, delete_module, performance_distribution, learning_style_distribution, completion_over_time, quiz_performance, top_performers, add_student, delete_student, student_quizzes, student_progress_details

from users.views import test_gemini_api

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', index_view, name='index'),
    #path('', login_view, name='home'),
    path('home/', index_view, name='index'),
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('Admindashboard/', admin_dashboard, name='admin_dashboard'),
    path('learn/', learning_view, name='learning_default'),
    path('learn/<int:lesson_id>/', learning_view, name='learning'),
    path('complete/<int:lesson_id>/', complete_lesson, name='complete_lesson'),
    path('progress/', include('progress.urls')),
    path('admin_login/', include('adminPanel.urls')),
    path('engine/', include('engine.urls')),
    #path('', views.dashboard_view, name='dashboard'),
    path('learning/<int:lesson_id>/',learning_view, name='learning'),
    path('learning/', learning_view, name='learning_default'),
    path('complete-lesson/<int:lesson_id>/', complete_lesson, name='complete_lesson'),
    path('update-lesson-time/<int:lesson_id>/',update_lesson_time, name='update_lesson_time'),
    path('course/<int:course_id>/', course_detail, name='course_detail'),
    path('api/generate-course/', generate_course, name='generate_course'),
    path('complete-lesson/<int:lesson_id>/', complete_lesson, name='complete_lesson'),
    path('api/complete-generated-topic/<int:topic_id>/', complete_generated_topic, name='complete_generated_topic'),
    path('api/complete-generated-topic/', complete_generated_topic, name='complete_generated_topic'),
    path('api/topic/<int:topic_id>/', get_topic_data_api, name='get_topic_data_api'),
    path('api/complete_topic/', complete_topic, name='complete_topic'),
    path('learning/', learning_default, name='learning_default'),
    path('api/complete_topic/', complete_topic, name='complete_topic'),
    path('progress-analysis/', progress_analysis_view, name='progress_analysis'),
    path('admin/delete-student/<int:student_id>/', delete_student, name='delete_student'),
    path('admin/student-details/<int:student_id>/', student_details, name='student_details'),
    path('admin/delete-module/<int:module_id>/', delete_module, name='delete_module'),
    path('admin/performance-distribution/', performance_distribution, name='performance_distribution'),
    path('admin/learning-style-distribution/', learning_style_distribution, name='learning_style_distribution'),
    path('admin/completion-over-time/', completion_over_time, name='completion_over_time'),
    path('admin/quiz-performance/', quiz_performance, name='quiz_performance'),
    path('admin/top-performers/', top_performers, name='top_performers'),
    path('admin/add-student/', add_student, name='add_student'),
    path('admin/delete-student/<int:student_id>/', delete_student, name='delete_student'),
    path('admin/student-quizzes/<int:student_id>/', student_quizzes, name='student_quizzes'),
    path('admin/student-progress/<int:student_id>/', student_progress_details, name='student_progress_details'),
    path('test-api/', test_gemini_api, name='test_api'),
    path('api/regenerate-topic/', regenerate_topic, name='regenerate_topic'),
    #path('admin-dashboard/', include('adminPanel.urls')),
]