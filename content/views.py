# content/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST
from django.conf import settings
from django.db.models import Q
from django.db import transaction
from .models import Course, Module, Lesson, GeneratedCourse, GeneratedChapter, GeneratedTopic, GeneratedQuiz, GeneratedQuestion, GeneratedAnswer, GeneratedCourseProgress, CompletedTopic, GeneratedTopicCompletion
from progress.models import UserProgress, ModuleProgress
from users.decorators import prevent_after_logout
import json
import google.generativeai as genai
import re
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger



@login_required
def get_topic_data_api(request, topic_id):
    try:
        topic = get_object_or_404(GeneratedTopic, id=topic_id)
        
        # Build the quiz data if a quiz exists for the topic
        quiz_data = None
        if hasattr(topic, 'quiz'):
            questions_list = []
            for question in topic.quiz.questions.all():
                answers_list = []
                for answer in question.answers.all():
                    answers_list.append({
                        'option_key': answer.option_key,
                        'answer_text': answer.answer_text,
                    })
                questions_list.append({
                    'question_text': question.question_text,
                    'answers': answers_list,
                    'correct_answer_key': question.correct_answer_key,
                })
            quiz_data = {'questions': questions_list}
        
        data = {
            'title': topic.title,
            'content': topic.content,
            'quiz': quiz_data,
        }
        
        return JsonResponse(data)
    except Http404:
        return JsonResponse({'error': 'Topic not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# Configure Gemini AI
genai.configure(api_key=settings.GEMINI_API_KEY)


# The modified dashboard_view
# content/views.py
@prevent_after_logout
@login_required
def dashboard_view(request):
    student = request.user
    
    # Get last accessed generated course for "Continue" button
    last_accessed_progress = GeneratedCourseProgress.objects.filter(student=request.user).order_by('-last_accessed_at').first()

    # Get generated courses for the user and apply pagination
    generated_courses_list = GeneratedCourse.objects.filter(user=request.user).order_by('-created_at')
    
    # Change the pagination limit from 6 to 5
    paginator = Paginator(generated_courses_list, 5) 
    page = request.GET.get('page')
    
    try:
        generated_courses = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        generated_courses = paginator.page(1)
    except EmptyPage:
        # If page is out of range, deliver last page of results.
        generated_courses = paginator.page(paginator.num_pages)

    # Existing logic for regular course progress data
    courses = Course.objects.all()
    progress_data = []
    for course in courses:
        completed_lessons = UserProgress.objects.filter(
            student=student,
            lesson__module__course=course,
            is_completed=True
        ).count()
        total_lessons = sum(module.lessons.count() for module in course.modules.all())
        progress_percentage = int((completed_lessons / total_lessons) * 100) if total_lessons > 0 else 0
        progress_data.append({
            'course': course,
            'progress_percentage': progress_percentage
        })

    context = {
        'student': student,
        'courses': progress_data,
        'generated_courses': generated_courses, # This is the paginated object
        'last_accessed_progress': last_accessed_progress
    }

    return render(request, 'dashboard.html', context)


@login_required
def learning_view(request, lesson_id=None):
    student = request.user
    
    # === Check if this is a generated course topic ===
    generated_course_id = request.GET.get('generated_course_id')
    generated_topic_id = request.GET.get('topic_id')
    
    if generated_course_id and generated_topic_id:
        try:
            course = get_object_or_404(GeneratedCourse, id=generated_course_id, user=student)
            topic = get_object_or_404(GeneratedTopic, id=generated_topic_id, chapter__course=course)
            
            # --- PROGRESS AND NAVIGATION LOGIC FOR GENERATED COURSES ---
            progress, created = GeneratedCourseProgress.objects.get_or_create(
                student=student, 
                course=course,
                defaults={'last_accessed_topic': topic}
            )
            if not created:
                progress.last_accessed_topic = topic
                progress.last_accessed_at = timezone.now()
                progress.save()

            total_topics = GeneratedTopic.objects.filter(chapter__course=course).count()
            completed_topics_count = GeneratedTopicCompletion.objects.filter(
                student=student,
                topic__chapter__course=course
            ).count()
            progress_percentage = int((completed_topics_count / total_topics) * 100) if total_topics > 0 else 0
            
            all_topics = GeneratedTopic.objects.filter(chapter__course=course).order_by('chapter__order', 'order')
            topic_list = list(all_topics)
            current_index = topic_list.index(topic) if topic in topic_list else -1
            
            previous_topic = topic_list[current_index - 1] if current_index > 0 else None
            next_topic = topic_list[current_index + 1] if current_index < len(topic_list) - 1 else None
            
            quiz_questions = []
            if hasattr(topic, 'quiz'):
                questions_qs = topic.quiz.questions.all().prefetch_related('answers')
                for question in questions_qs:
                    try:
                        correct_answer = question.answers.get(is_correct=True)
                        question.correct_answer_key = correct_answer.option_key
                    except GeneratedAnswer.DoesNotExist:
                        question.correct_answer_key = ''
                quiz_questions = list(questions_qs)
                
            return render(request, 'learning.html', {
                'course': course,
                'module': topic.chapter,
                'lesson': topic,
                'progress_percentage': progress_percentage,
                'previous_lesson': previous_topic,
                'next_lesson': next_topic,
                'is_generated': True,
                'quiz_questions': quiz_questions,
            })
        except GeneratedCourse.DoesNotExist:
            raise Http404("Generated course not found")
        except GeneratedTopic.DoesNotExist:
            raise Http404("Generated topic not found")
    
    # === Regular lessons ===
    if lesson_id:
        lesson = get_object_or_404(Lesson, id=lesson_id)
    else:
        incomplete_lessons = Lesson.objects.exclude(
            progress__student=student,
            progress__is_completed=True
        ).order_by('module__order', 'order')
        
        lesson = incomplete_lessons.first()
        
        if not lesson:
            lesson = Lesson.objects.order_by('module__order', 'order').first()
        
        if lesson:
            return redirect('learning', lesson_id=lesson.id)
        else:
            return redirect('dashboard')
    
    progress, created = UserProgress.objects.get_or_create(
        student=student,
        lesson=lesson,
        defaults={'last_accessed': timezone.now()}
    )
    if not created:
        progress.last_accessed = timezone.now()
        progress.save()
    
    module = lesson.module
    completed_lessons_count = UserProgress.objects.filter(
        student=student,
        lesson__module=module,
        is_completed=True
    ).count()
    total_lessons_count = module.lessons.count()
    progress_percentage = int((completed_lessons_count / total_lessons_count) * 100) if total_lessons_count else 0
    
    def get_next_lesson(student, current_lesson):
        next_lesson = Lesson.objects.filter(
            module__order__gte=current_lesson.module.order,
            order__gt=current_lesson.order
        ).order_by('module__order', 'order').first()
        return next_lesson
    
    def get_previous_lesson(student, current_lesson):
        previous_lesson = Lesson.objects.filter(
            module__order__lte=current_lesson.module.order,
            order__lt=current_lesson.order
        ).order_by('-module__order', '-order').first()
        return previous_lesson
        
    previous_lesson = get_previous_lesson(student, lesson)
    next_lesson = get_next_lesson(student, lesson)
    
    # This return statement was missing in your regular lesson logic
    return render(request, 'learning.html', {
        'lesson': lesson,
        'module': module,
        'progress_percentage': progress_percentage,
        'previous_lesson': previous_lesson,
        'next_lesson': next_lesson,
        'is_generated': False,
    })
    
@csrf_protect
@require_POST
@login_required
def generate_course(request):
    try:
        data = json.loads(request.body)
        
        # Extract user inputs
        course_name = data.get('name')
        description = data.get('description', '')
        no_of_chapters = data.get('noOfChapters', 1)
        level = data.get('level', 'beginner')
        
        # Formulate a simplified and direct prompt for Gemini
        user_prompt = f"""
        Generate a comprehensive and detailed course outline for a {level} level e-learning course titled "{course_name}".
        The course should have exactly {no_of_chapters} chapters.
        Each chapter must have a title, a brief description, and 3-5 sub-topics.
        For each sub-topic, include a detailed "content" section of at least 250 words, formatted using markdown.
        For each sub-topic, generate a simple multiple-choice quiz with 3 questions. Each question must have exactly 4 answer options (A, B, C, D) and a single correct answer key.
        The entire response must be a single, valid JSON object with the following exact structure. Do not include any other text, explanations, or code block delimiters (` ```json `).
        
        {{
            "title": "Course Title",
            "description": "Course Description",
            "chapters": [
                {{
                    "title": "Chapter Title",
                    "topics": [
                        {{
                            "title": "Topic Title",
                            "content": "Detailed topic content here...",
                            "quiz": {{
                                "questions": [
                                    {{
                                        "question_text": "...",
                                        "answers": [
                                            {{ "answer_text": "...", "option_key": "A" }},
                                            {{ "answer_text": "...", "option_key": "B" }},
                                            {{ "answer_text": "...", "option_key": "C" }},
                                            {{ "answer_text": "...", "option_key": "D" }}
                                        ],
                                        "correct_answer_key": "B"
                                    }}
                                ]
                            }}
                        }}
                    ]
                }}
            ]
        }}
        """

        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(user_prompt, request_options={"timeout": 600})
        
        # Check for a valid AI response object first
        if not response or not response.text:
            return JsonResponse({'success': False, 'error': 'AI returned an empty or invalid response object.'}, status=500)
            
        ai_content = response.text.strip()
        
        # Strip the markdown code block before parsing
        if ai_content.startswith('```json'):
            ai_content = ai_content.removeprefix('```json').removesuffix('```').strip()
        
        print("--- CLEANED AI RESPONSE START ---")
        print(ai_content)
        print("--- CLEANED AI RESPONSE END ---")

        # Now, attempt to parse the cleaned content
        generated_data = json.loads(ai_content)
        
        with transaction.atomic():
            generated_course = GeneratedCourse.objects.create(
                user=request.user,
                title=generated_data.get('title', course_name),
                description=generated_data.get('description', description),
                category=data.get('category', ''),
                difficulty=level,
                include_video=data.get('includeVideo', False),
                chapters_count=len(generated_data.get('chapters', [])),
                generated_content=generated_data
            )
            
            first_topic = None
            for chapter_data in generated_data.get('chapters', []):
                generated_chapter = GeneratedChapter.objects.create(
                    course=generated_course,
                    title=chapter_data.get('title', 'Untitled Chapter'),
                    duration=chapter_data.get('duration', '10 min'),
                    image_prompt=chapter_data.get('image_prompt', 'An AI-generated image for the chapter.'),
                    order=chapter_data.get('order', 0)
                )
                
                for topic_order, topic_data in enumerate(chapter_data.get('topics', [])):
                    generated_topic = GeneratedTopic.objects.create(
                        chapter=generated_chapter,
                        title=topic_data.get('title', 'Untitled Topic'),
                        content=topic_data.get('content', 'No content provided.'),
                        description=topic_data.get('description', ''),
                        order=topic_order
                    )
                    
                    if not first_topic:
                        first_topic = generated_topic
                        
                    if 'quiz' in topic_data and topic_data['quiz'] and topic_data['quiz'].get('questions'):
                        quiz = GeneratedQuiz.objects.create(topic=generated_topic)
                        for question_data in topic_data['quiz']['questions']:
                            question = GeneratedQuestion.objects.create(
                                quiz=quiz,
                                question_text=question_data['question_text'],
                            )
                            for answer_data in question_data['answers']:
                                GeneratedAnswer.objects.create(
                                    question=question,
                                    answer_text=answer_data['answer_text'],
                                    option_key=answer_data.get('option_key'),
                                    is_correct=(answer_data.get('option_key') == question_data.get('correct_answer_key'))
                                )

            if first_topic:
                return JsonResponse({
                    'success': True,
                    'course_id': generated_course.id,
                    'first_topic_id': first_topic.id
                })
            else:
                return JsonResponse({'success': False, 'error': 'AI did not generate any topics.'}, status=500)
    
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Failed to parse JSON from AI response. The response may be malformed. Details: {e}'
        }, status=500)
    except Exception as e:
        print(f"Unexpected Error: {e}")
        return JsonResponse({
            'success': False,
            'error': f'An unexpected error occurred: {e}'
        }, status=500)


@login_required
def learning_default(request):
    generated_course_id = request.GET.get('generated_course_id')
    topic_id = request.GET.get('topic_id')
    
    if not generated_course_id or not topic_id:
        raise Http404("Generated course ID and topic ID are required.")
    
    # Use 'user' as the field name to find the course, matching GeneratedCourse model
    course = get_object_or_404(GeneratedCourse, id=generated_course_id, user=request.user)
    topic = get_object_or_404(GeneratedTopic, id=topic_id, chapter__course=course)

    # Use update_or_create to correctly update the progress
    progress, created = GeneratedCourseProgress.objects.update_or_create(
        student=request.user, 
        course=course,
        defaults={'last_accessed_topic': topic}
    )

    # Calculate overall course progress for the progress bar
    total_topics = GeneratedTopic.objects.filter(chapter__course=course).count()
    completed_topics = GeneratedTopicCompletion.objects.filter(
        student=request.user,
        topic__chapter__course=course
    ).count()

    progress_percentage = 0
    if total_topics > 0:
        progress_percentage = int((completed_topics / total_topics) * 100)

    context = {
        'course': course,
        'topic': topic,
        'is_generated': True,
        'progress_percentage': progress_percentage
    }
    return render(request, 'learning.html', context)



@login_required
def complete_lesson(request, lesson_id):
    """Mark a lesson as completed"""
    if request.method == 'POST':
        lesson = get_object_or_404(Lesson, id=lesson_id)
        student = request.user
        
        # Update or create progress record
        progress, created = UserProgress.objects.update_or_create(
            student=student,
            lesson=lesson,
            defaults={
                'is_completed': True,
                'completed_at': timezone.now(),
                'score': request.POST.get('score', 100),
                'last_accessed': timezone.now()
            }
        )
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'progress_id': progress.id})
        
        #messages.success(request, f"Lesson '{lesson.title}' marked as completed!")
        return redirect('learning', lesson_id=lesson_id)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

@login_required
def complete_generated_topic(request, topic_id):
    topic = get_object_or_404(GeneratedTopic, id=topic_id)
    student = request.user
    
    # Use update_or_create to set the topic as completed
    UserProgress.objects.update_or_create(
        student=student,
        generated_topic=topic,
        defaults={
            'is_completed': True,
            'completed_at': timezone.now(),
        }
    )
    messages.success(request, f"Topic '{topic.title}' marked as completed!")
    
    # Redirect back to the same page with the next lesson
    course_id = topic.chapter.course.id
    next_topic = GeneratedTopic.objects.filter(
        chapter__course=topic.chapter.course,
        chapter__order__gte=topic.chapter.order,
        order__gt=topic.order
    ).order_by('chapter__order', 'order').first()
    
    if next_topic:
        return redirect(f"/learning/?generated_course_id={course_id}&topic_id={next_topic.id}")
    else:
        # If no next topic, redirect to the course learning page to show completion
        return redirect(f"/learning/?generated_course_id={course_id}&topic_id={topic.id}")
    
@login_required
def update_lesson_time(request, lesson_id):
    """Update time spent on a lesson"""
    if request.method == 'POST':
        lesson = get_object_or_404(Lesson, id=lesson_id)
        student = request.user
        time_spent = request.POST.get('time_spent')
        
        if time_spent:
            progress, created = UserProgress.objects.get_or_create(
                student=student,
                lesson=lesson,
                defaults={'last_accessed': timezone.now()}
            )
            
            if not created:
                progress.last_accessed = timezone.now()
                # You might want to add time tracking logic here
                progress.save()
            
            return JsonResponse({'success': True})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
def course_detail(request, course_id):
    """Detailed view of a course with module progress"""
    course = get_object_or_404(Course, id=course_id)
    student = request.user
    
    module_progress = []
    for module in course.modules.all():
        completed_lessons = UserProgress.objects.filter(
            student=student,
            lesson__module=module,
            is_completed=True
        ).count()
        total_lessons = module.lessons.count()
        progress_percentage = int((completed_lessons / total_lessons) * 100) if total_lessons > 0 else 0
        
        module_progress.append({
            'module': module,
            'completed_lessons': completed_lessons,
            'total_lessons': total_lessons,
            'progress_percentage': progress_percentage
        })
    
    return render(request, 'learning.html', {
        'course': course,
        'module_progress': module_progress,
        'student': student
    })
    
# New views to add to content/views.py

@login_required
def learning_default(request):
    generated_course_id = request.GET.get('generated_course_id')
    topic_id = request.GET.get('topic_id')
    
    if not generated_course_id or not topic_id:
        raise Http404("Generated course ID and topic ID are required.")
    
    # Corrected: Use 'user' instead of 'student'
    course = get_object_or_404(GeneratedCourse, id=generated_course_id, user=request.user)
    topic = get_object_or_404(GeneratedTopic, id=topic_id, chapter__course=course)

    # Update the user's progress
    progress, created = GeneratedCourseProgress.objects.get_or_create(
        student=request.user, 
        course=course,
        defaults={'last_accessed_topic': topic}
    )
    if not created:
        progress.last_accessed_topic = topic
        progress.save()

    # Calculate overall course progress for the progress bar
    total_topics = GeneratedTopic.objects.filter(chapter__course=course).count()
    completed_topics = GeneratedTopicCompletion.objects.filter(
        student=request.user,
        topic__chapter__course=course
    ).count()

    progress_percentage = 0
    if total_topics > 0:
        progress_percentage = int((completed_topics / total_topics) * 100)

    context = {
        'course': course,
        'topic': topic,
        'is_generated': True,
        'progress_percentage': progress_percentage
    }
    return render(request, 'learning.html', context)

@require_POST
@login_required
@csrf_protect
def complete_topic(request):
    try:
        topic_id = request.POST.get('topic_id')
        if not topic_id:
            return JsonResponse({'success': False, 'error': 'Topic ID is required.'})

        topic = get_object_or_404(GeneratedTopic, id=topic_id)
        
        # Mark the topic as complete
        completion, created = GeneratedTopicCompletion.objects.get_or_create(
            student=request.user,
            topic=topic
        )

        return JsonResponse({'success': True, 'completed': created})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def get_topic_data_api(request, topic_id):
    try:
        topic = get_object_or_404(GeneratedTopic, id=topic_id)
        
        # Build the quiz data if a quiz exists for the topic
        quiz_data = None
        if hasattr(topic, 'quiz'):
            questions_list = []
            for question in topic.quiz.questions.all():
                answers_list = []
                for answer in question.answers.all():
                    answers_list.append({
                        'option_key': answer.option_key,
                        'answer_text': answer.answer_text,
                    })
                questions_list.append({
                    'id': question.id,
                    'question_text': question.question_text,
                    'answers': answers_list,
                    'correct_answer_key': question.correct_answer_key
                })
            quiz_data = {'questions': questions_list}

        # Check if the topic is completed
        is_completed = GeneratedTopicCompletion.objects.filter(student=request.user, topic=topic).exists()

        data = {
            'title': topic.title,
            'content': topic.content,
            'quiz': quiz_data,
            'is_completed': is_completed
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

    


import google.generativeai as genai
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from .models import GeneratedTopic, GeneratedTopicCompletion, GeneratedQuestion, GeneratedAnswer

@require_POST
@login_required
@csrf_protect
def complete_generated_topic(request):
    try:
        data = json.loads(request.body)
        topic_id = data.get('topic_id')
        user_answers = data.get('answers', {})

        if not topic_id:
            return JsonResponse({'success': False, 'error': 'Topic ID is required.'}, status=400)

        topic = get_object_or_404(GeneratedTopic, id=topic_id)
        student = request.user
        
        correct_answers_count = 0
        total_questions_count = topic.quiz.questions.count() if hasattr(topic, 'quiz') else 0

        if total_questions_count > 0:
            for question in topic.quiz.questions.all():
                try:
                    correct_answer = question.answers.get(is_correct=True)
                    user_selected_option = user_answers.get(str(question.id))
                    
                    if user_selected_option == correct_answer.option_key:
                        correct_answers_count += 1
                except GeneratedAnswer.DoesNotExist:
                    continue
        
        score_percentage = int((correct_answers_count / total_questions_count) * 100) if total_questions_count > 0 else 0
        
        with transaction.atomic():
            completion, created = GeneratedTopicCompletion.objects.get_or_create(
                student=student,
                topic=topic,
                defaults={'score': score_percentage}
            )
            if not created:
                completion.score = score_percentage
                completion.save()

            progress, _ = GeneratedCourseProgress.objects.get_or_create(
                student=student,
                course=topic.chapter.course
            )
            progress.last_accessed_topic = topic
            progress.save()
        
        performance_data = []
        if total_questions_count > 0:
            for question in topic.quiz.questions.all():
                user_selected_option = user_answers.get(str(question.id))
                correct_answer = question.answers.get(is_correct=True)
                is_correct = user_selected_option == correct_answer.option_key
                performance_data.append({
                    'question_text': question.question_text,
                    'user_answer': user_selected_option,
                    'correct_answer_key': correct_answer.option_key,
                    'is_correct': is_correct
                })
        
        prompt = f"""
        Analyze the student's quiz performance on the topic "{topic.title}" and provide a personalized feedback summary.
        The student's results are: {json.dumps(performance_data, indent=2)}.
        Their score is {score_percentage}%.
        The feedback should:
        1. Start with a positive and encouraging note.
        2. Summarize their overall performance.
        3. For any incorrect answers, briefly explain why the correct answer is right and suggest areas for review.
        4. End with a motivational closing.
        """
        
        model = genai.GenerativeModel('gemini-1.5-pro')
        ai_response = model.generate_content(prompt)
        ai_feedback = ai_response.text

        next_topic = GeneratedTopic.objects.filter(
            chapter__course=topic.chapter.course,
            chapter__order__gte=topic.chapter.order,
            order__gt=topic.order
        ).order_by('chapter__order', 'order').first()

        response_data = {
            'success': True,
            'message': 'Quiz submitted and progress saved.',
            'ai_feedback': ai_feedback,
            'course_id': topic.chapter.course.id,
            'score': score_percentage,
        }
        
        if next_topic:
            response_data['next_topic_id'] = next_topic.id
            
        return JsonResponse(response_data)

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data in request body.'}, status=400)
    except GeneratedTopic.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Topic not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)