# engine/urls.py
from django.urls import path
from . import views

app_name = 'engine'

urlpatterns = [
    path('dashboard/', views.adaptive_dashboard, name='adaptive_dashboard'),
    path('recommendations/', views.content_recommendations, name='content_recommendations'),
    path('record-engagement/', views.record_engagement, name='record_engagement'),
    path('insights/', views.learning_insights, name='learning_insights'),
    path('integrate-content/<str:topic>/', views.integrate_external_content, name='integrate_content'),
]