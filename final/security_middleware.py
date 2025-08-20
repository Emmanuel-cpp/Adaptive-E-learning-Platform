# security_middleware.py
from django.core.cache import cache
from django.conf import settings
from django.contrib.auth import get_user_model

class LoginAttemptMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.path == '/login/' and request.method == 'POST':
            username = request.POST.get('username')
            if username:
                attempt_count = cache.get(f'login_attempts_{username}', 0)
                if attempt_count >= settings.MAX_LOGIN_ATTEMPTS:
                    from django.contrib import messages
                    messages.error(request, 'Account temporarily locked due to too many failed login attempts.')
                    from django.shortcuts import redirect
                    return redirect('login')

class NoCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response