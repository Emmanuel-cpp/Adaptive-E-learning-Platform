from django.contrib import admin
from django.urls import path
from users.views import login_view, register_view, logout_view, index_view
from adminPanel.views import admin_login_view
from content.views import dashboard_view, learning_view, complete_lesson
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
    #path('admin-dashboard/', include('adminPanel.urls')),
]