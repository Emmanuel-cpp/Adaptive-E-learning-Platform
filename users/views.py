# users/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import RegistrationForm
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.conf import settings
from .models import LoginAttempt

def index_view(request):
    return render(request, 'index.html')

@csrf_exempt
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Check if account is locked using database
        if LoginAttempt.is_locked(username):
            messages.error(request, 'Account temporarily locked due to too many failed login attempts. Please try again later.')
            return render(request, 'login.html')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Reset attempt count on successful login
            LoginAttempt.reset_attempts(username)
            login(request, user)
            
            # Set session expiry on browser close
            request.session.set_expiry(0)
            
            return redirect('dashboard')
        else:
            # Record failed attempt in database
            attempt = LoginAttempt.record_failed_attempt(username, request.META.get('REMOTE_ADDR'))
            
            remaining_attempts = settings.MAX_LOGIN_ATTEMPTS - attempt.attempts
            if remaining_attempts > 0:
                messages.error(request, f'Invalid username or password.')
            else:
                messages.error(request, 'Account temporarily locked due to too many failed login attempts. Please try again later.')
    
    return render(request, 'login.html')

@csrf_exempt
def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
        else:
            # Show form errors in messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = RegistrationForm()
    
    return render(request, 'register.html', {'form': form})

def logout_view(request):
    # Clear session completely
    request.session.flush()
    
    # Create a response to redirect
    response = redirect('index')
    
    # Add headers to prevent caching
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    
    return response

@login_required
def temp_dashboard(request):
    return render(request, 'dashboard.html')