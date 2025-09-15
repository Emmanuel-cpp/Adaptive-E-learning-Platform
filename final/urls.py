from django.contrib import admin
from django.urls import path
from users.views import login_view, register_view, logout_view, index_view
from adminPanel.views import admin_login_view
from content.views import dashboard_view, learning_view, complete_lesson, update_lesson_time, course_detail,generate_course, complete_generated_topic, get_topic_data_api, complete_topic, learning_default
from adminPanel.views import admin_dashboard
from django.urls import include


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
    path('api/topic/<int:topic_id>/', get_topic_data_api, name='get_topic_data_api'),
    path('api/complete_topic/', complete_topic, name='complete_topic'),
    path('learning/', learning_default, name='learning_default'),
    path('api/complete_topic/', complete_topic, name='complete_topic'),
    #path('admin-dashboard/', include('adminPanel.urls')),
]