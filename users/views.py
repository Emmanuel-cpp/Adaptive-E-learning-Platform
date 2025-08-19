from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .forms import RegistrationForm
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

def index_view(request):
    return render(request, 'index.html')

@csrf_exempt
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            return redirect('dashboard')  # Make sure 'dashboard' URL name exists
        else:
            messages.error(request, 'Invalid username or password')
    return render(request, 'auth.html', {'form_type': 'login'})

@csrf_exempt
def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # Log the user in after registration
            return redirect('dashboard')
        else:
            # Show form errors in messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = RegistrationForm()
    
    return render(request, 'auth.html', {'form': form, 'form_type': 'register'})

def logout_view(request):
    logout(request)
    return redirect('index')

# Add this temporary dashboard view for testing
@login_required
def temp_dashboard(request):
    return render(request, 'dashboard.html')