# adminPanel/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.admin_login_view, name='admin_login'),
    path('adminDashboard/', views.admin_dashboard, name='Admindashboard'),
]