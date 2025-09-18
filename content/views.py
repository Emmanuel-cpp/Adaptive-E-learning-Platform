# content/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone

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
import logging
logger = logging.getLogger(__name__)




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
        return JsonResponse({''}, status=404)
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
            
            # Check if this is a regenerated topic and get the original if needed
            original_topic = None
            if hasattr(topic, 'is_regenerated') and topic.is_regenerated and hasattr(topic, 'original_topic') and topic.original_topic:
                original_topic = topic.original_topic
            
            # Check if topic is completed
            try:
                completion = GeneratedTopicCompletion.objects.get(student=student, topic=topic)
                topic_completed = completion.passed if hasattr(completion, 'passed') else False
            except GeneratedTopicCompletion.DoesNotExist:
                topic_completed = False
            
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
                topic__chapter__course=course,
                passed=True
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
                'original_topic': original_topic,
                'progress_percentage': progress_percentage,
                'previous_lesson': previous_topic,
                'next_lesson': next_topic,
                'is_generated': True,
                'quiz_questions': quiz_questions,
                'topic_completed': topic_completed,
                'is_regenerated': topic.is_regenerated if hasattr(topic, 'is_regenerated') else False,
            })
            
        except (GeneratedCourse.DoesNotExist, GeneratedTopic.DoesNotExist):
            raise Http404("Course or topic not found")
        except Exception as e:
            # Log the error and return a user-friendly message
            logger.error(f"Error in learning_view (generated course): {str(e)}")
            return render(request, 'error.html', {
                'error_message': 'An error occurred while loading the lesson. Please try again.'
            })
    
    # === Regular lessons ===
    try:
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
        
        return render(request, 'learning.html', {
            'lesson': lesson,
            'module': module,
            'progress_percentage': progress_percentage,
            'previous_lesson': previous_lesson,
            'next_lesson': next_lesson,
            'is_generated': False,
            'topic_completed': False,  # Not applicable for regular lessons
            'is_regenerated': False,   # Not applicable for regular lessons
        })
        
    except Exception as e:
        # Log the error and return a user-friendly message
        logger.error(f"Error in learning_view (regular lesson): {str(e)}")
        return render(request, 'error.html', {
            'error_message': 'An error occurred while loading the lesson. Please try again.'
        })
    
@csrf_protect
@require_POST
@login_required
def generate_course(request):
    try:
        # Parse the request data
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON data.'}, status=400)
            
        lesson_topic = data.get('name', '').strip()
        if not lesson_topic:
            return JsonResponse({'success': False, 'error': 'Lesson topic is required.'}, status=400)

        description = data.get('description', '').strip()
        no_of_chapters = max(1, min(int(data.get('noOfChapters', 1)), 10))
        level = data.get('level', 'beginner')

        # Check API key
        if not settings.GEMINI_API_KEY:
            return JsonResponse({'success': False, 'error': 'API key not configured.'}, status=500)

        # Strict C++ AI prompt
        user_prompt = f"""
        Generate a comprehensive and detailed lesson plan for a {level} level C++ course on the topic "{lesson_topic}".
        The course should have exactly {no_of_chapters} chapters.
        Each chapter must have a title, description, and 3-5 sub-topics.
        Each sub-topic should have detailed content (min 250 words) with C++ code examples in markdown.
        Include a multiple-choice quiz (3 questions per sub-topic, 4 options A-D, one correct answer).

        Respond ONLY with valid JSON in this structure:
        {{
            "title": "Course Title",
            "description": "Course Description",
            "chapters": [
                {{
                    "title": "Chapter Title",
                    "description": "Chapter description",
                    "topics": [
                        {{
                            "title": "Topic Title",
                            "content": "Detailed topic content...",
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

        # Generate content with better error handling
        try:
            # Use a more reliable model
            model = genai.GenerativeModel('gemini-2.0-flash-lite', generation_config={"response_mime_type": "application/json"})
            response = model.generate_content(user_prompt, request_options={"timeout": 120})  # Reduced timeout
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'AI service error: {str(e)}'}, status=500)

        if not response or not response.text:
            return JsonResponse({'success': False, 'error': 'AI returned empty response.'}, status=500)

        # Parse the response
        try:
            generated_data = json.loads(response.text)
        except json.JSONDecodeError as e:
            return JsonResponse({'success': False, 'error': f'Invalid JSON from AI: {str(e)}'}, status=500)

        if not generated_data.get('chapters') or not isinstance(generated_data['chapters'], list):
            return JsonResponse({'success': False, 'error': 'Invalid AI course structure.'}, status=500)

        # Save course and lessons
        with transaction.atomic():
            generated_course = GeneratedCourse.objects.create(
                user=request.user,
                title=generated_data.get('title', lesson_topic),
                description=generated_data.get('description', description),
                difficulty=level,
                include_video=data.get('includeVideo', False),
                chapters_count=len(generated_data.get('chapters', [])),
                generated_content=generated_data
            )

            first_topic = None
            for chapter_idx, chapter_data in enumerate(generated_data['chapters']):
                generated_chapter = GeneratedChapter.objects.create(
                    course=generated_course,
                    title=chapter_data.get('title', f'Chapter {chapter_idx+1}'),
                    duration=chapter_data.get('duration', '10 min'),
                    order=chapter_idx
                )
                for topic_idx, topic_data in enumerate(chapter_data.get('topics', [])):
                    generated_topic = GeneratedTopic.objects.create(
                        chapter=generated_chapter,
                        title=topic_data.get('title', f'Topic {topic_idx+1}'),
                        content=topic_data.get('content', 'No content provided.'),
                        description=topic_data.get('description', ''),
                        order=topic_idx
                    )
                    if not first_topic: 
                        first_topic = generated_topic

                    if 'quiz' in topic_data and topic_data['quiz'].get('questions'):
                        quiz = GeneratedQuiz.objects.create(topic=generated_topic)
                        for q_idx, question_data in enumerate(topic_data['quiz']['questions']):
                            question = GeneratedQuestion.objects.create(
                                quiz=quiz,
                                question_text=question_data.get('question_text', f'Question {q_idx+1}'),
                                order=q_idx
                            )
                            for a_idx, answer_data in enumerate(question_data.get('answers', [])):
                                is_correct = answer_data.get('option_key') == question_data.get('correct_answer_key')
                                GeneratedAnswer.objects.create(
                                    question=question,
                                    answer_text=answer_data.get('answer_text', f'Answer {a_idx+1}'),
                                    option_key=answer_data.get('option_key', chr(65+a_idx)),
                                    is_correct=is_correct,
                                    order=a_idx
                                )

        if first_topic:
            return JsonResponse({
                'success': True, 
                'course_id': generated_course.id, 
                'first_topic_id': first_topic.id
            })
        else:
            return JsonResponse({'success': False, 'error': 'AI did not generate any topics.'}, status=500)

    except Exception as e:
        # Log the error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error generating course: {str(e)}")
        
        return JsonResponse({'success': False, 'error': f'Unexpected error: {str(e)}'}, status=500)

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

"""
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
    #messages.success(request, f"Topic '{topic.title}' marked as completed!")
    
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
 """   
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
        data = json.loads(request.body)
        topic_id = data.get('topic_id')
        user_answers = data.get('answers', {})

        if not topic_id:
            return JsonResponse({'success': False, 'error': 'Topic ID is required.'}, status=400)

        topic = get_object_or_404(GeneratedTopic, id=topic_id)
        student = request.user
        
        # Calculate quiz score
        correct_answers_count = 0
        total_questions = topic.quiz.questions.count() if hasattr(topic, 'quiz') else 0
        
        if total_questions > 0:
            for question in topic.quiz.questions.all():
                try:
                    correct_answer = question.answers.get(is_correct=True)
                    user_selected_option = user_answers.get(str(question.id))
                    
                    if user_selected_option == correct_answer.option_key:
                        correct_answers_count += 1
                except GeneratedAnswer.DoesNotExist:
                    continue
        
        score_percentage = int((correct_answers_count / total_questions) * 100) if total_questions > 0 else 100
        
        # Update or create completion record with score
        completion, created = GeneratedTopicCompletion.objects.update_or_create(
            student=student,
            topic=topic,
            defaults={'score': score_percentage}
        )
        
        # Update overall course progress
        course = topic.chapter.course
        total_topics = GeneratedTopic.objects.filter(chapter__course=course).count()
        completed_topics = GeneratedTopicCompletion.objects.filter(
            student=student,
            topic__chapter__course=course
        ).count()
        
        course_progress = int((completed_topics / total_topics) * 100) if total_topics > 0 else 0
        
        return JsonResponse({
            'success': True,
            'score': score_percentage,
            'course_progress': course_progress,
            'message': 'Topic completed successfully!'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
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
from django.db import models


@require_POST
@login_required
@csrf_protect
def complete_generated_topic(request, topic_id=None):
    try:
        data = json.loads(request.body)
        topic_id = data.get('topic_id')
        user_answers = data.get('answers', {})

        if not topic_id:
            return JsonResponse({'success': False, 'error': 'Topic ID is required.'}, status=400)

        topic = get_object_or_404(GeneratedTopic, id=topic_id)
        student = request.user
        course = topic.chapter.course
        
        # Calculate quiz score and collect wrong answers
        correct_answers_count = 0
        total_questions = topic.quiz.questions.count() if hasattr(topic, 'quiz') else 0
        wrong_answers = []  # Store wrong answers for remedial resources
        
        if total_questions > 0:
            for question in topic.quiz.questions.all():
                try:
                    correct_answer = question.answers.get(is_correct=True)
                    user_selected_option = user_answers.get(str(question.id))
                    
                    if user_selected_option == correct_answer.option_key:
                        correct_answers_count += 1
                    else:
                        # Add wrong answer details - use consistent field names
                        wrong_answers.append({
                            'question': question.question_text,
                            'user_answer': user_selected_option,
                            'correct_answer': correct_answer.option_key,
                            'correct_answer_text': correct_answer.answer_text
                        })
                except GeneratedAnswer.DoesNotExist:
                    continue
        
        score_percentage = int((correct_answers_count / total_questions) * 100) if total_questions > 0 else 100
        
        # Check if student passed (50% or higher)
        passed = score_percentage >= 50
        
        # First, try to get the existing completion record
        try:
            completion = GeneratedTopicCompletion.objects.get(student=student, topic=topic)
            # If it exists, update it
            completion.score = score_percentage
            completion.passed = passed
            completion.wrong_answers = wrong_answers
            completion.attempt_count += 1  # Manually increment the attempt count
            completion.save()
        except GeneratedTopicCompletion.DoesNotExist:
            # If it doesn't exist, create a new one
            completion = GeneratedTopicCompletion.objects.create(
                student=student,
                topic=topic,
                score=score_percentage,
                passed=passed,
                wrong_answers=wrong_answers,
                attempt_count=1  # Start with 1 for new records
            )
        
        # Update overall course progress (only count passed topics)
        total_topics = GeneratedTopic.objects.filter(chapter__course=course).count()
        completed_topics = GeneratedTopicCompletion.objects.filter(
            student=student,
            topic__chapter__course=course,
            passed=True
        ).count()
        
        course_progress = int((completed_topics / total_topics) * 100) if total_topics > 0 else 0
        
        # Get specific C++ remedial resources with wrong answers
        remedial_resources = get_cpp_remedial_resources(topic.title, score_percentage, wrong_answers)
        
        # Generate AI feedback
        ai_feedback = generate_ai_feedback(topic, user_answers, score_percentage, passed, remedial_resources)

        # Find or generate next topic based on performance
        next_topic = None
        if passed:
            next_topic = get_or_generate_next_topic(course, topic, student, score_percentage)
        
        response_data = {
            'success': True,
            'passed': passed,
            'score': score_percentage,
            'ai_feedback': ai_feedback,
            'course_progress': course_progress,
            'remedial_resources': remedial_resources,
            'course_id': course.id,
        }
        
        if next_topic:
            response_data['next_topic_id'] = next_topic.id
            
        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error in complete_generated_topic: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
def regenerate_simpler_topic(original_topic, student, score_percentage, wrong_answers):
    """
    Regenerate a simpler version of a topic based on the student's performance
    """
    try:
        # Determine the complexity level based on the score
        if score_percentage < 20:
            complexity = "very basic"
            examples_multiplier = 2  # Include more examples
        elif score_percentage < 35:
            complexity = "basic"
            examples_multiplier = 1.5
        else:
            complexity = "simplified"
            examples_multiplier = 1.2
        
        # Analyze wrong answers to understand specific difficulties
        difficulty_analysis = ""
        if wrong_answers:
            difficulty_analysis = "The student specifically struggled with:\n"
            for i, wrong in enumerate(wrong_answers, 1):
                question_text = wrong.get('question', wrong.get('question_text', 'Unknown question'))
                user_answer = wrong.get('user_answer', 'No answer')
                correct_answer = wrong.get('correct_answer', wrong.get('correct_answer_text', 'Unknown answer'))
                
                difficulty_analysis += f"{i}. {question_text}\n"
                difficulty_analysis += f"   Their answer: {user_answer}\n"
                difficulty_analysis += f"   Correct answer: {correct_answer}\n"
        
        prompt = f"""
        Create a simpler version of the C++ topic "{original_topic.title}" for a student who scored {score_percentage}%.
        
        {difficulty_analysis}
        
        Please generate a new version that:
        1. Is at a {complexity} level
        2. Uses simpler language and more concrete examples
        3. Focuses on the specific concepts the student struggled with
        4. Includes {examples_multiplier}x more examples than the original
        5. Breaks down complex concepts into smaller, more digestible parts
        6. Uses analogies and real-world examples where appropriate
        
        Also generate a simpler quiz with 3 questions that focus on the core concepts.
        
        Respond with JSON in this format:
        {{
            "title": "Simplified: [Original Title]",
            "content": "Simplified content...",
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
        """
        
        model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})
        response = model.generate_content(prompt)
        
        # Try to parse the response
        try:
            topic_data = json.loads(response.text)
        except json.JSONDecodeError:
            # If it's not valid JSON, try to extract JSON from the response
            import re
            # Try to find JSON in the response
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                try:
                    topic_data = json.loads(json_match.group())
                except json.JSONDecodeError:
                    logger.error(f"Could not parse extracted JSON: {json_match.group()}")
                    return None
            else:
                logger.error(f"Could not extract JSON from AI response: {response.text}")
                return None
        
        # Create a new chapter for the regenerated topic
        original_chapter = original_topic.chapter
        new_chapter_order = original_chapter.order + 0.1  # Place it right after the original
        
        # Check if a chapter for regenerated topics already exists
        regenerated_chapter = GeneratedChapter.objects.filter(
            course=original_chapter.course,
            title=f"Reinforcement: {original_chapter.title}"
        ).first()
        
        if not regenerated_chapter:
            regenerated_chapter = GeneratedChapter.objects.create(
                course=original_chapter.course,
                title=f"Reinforcement: {original_chapter.title}",
                order=new_chapter_order
            )
        
        # Create the regenerated topic
        regenerated_topic = GeneratedTopic.objects.create(
            chapter=regenerated_chapter,
            title=topic_data.get('title', f"Simplified: {original_topic.title}"),
            content=topic_data.get('content', ''),
            order=0,
            is_regenerated=True,
            original_topic=original_topic
        )
        
        # Create quiz if provided
        if 'quiz' in topic_data and topic_data['quiz'].get('questions'):
            quiz = GeneratedQuiz.objects.create(topic=regenerated_topic)
            for q_idx, question_data in enumerate(topic_data['quiz']['questions']):
                question = GeneratedQuestion.objects.create(
                    quiz=quiz,
                    question_text=question_data.get('question_text', f'Question {q_idx+1}'),
                    order=q_idx
                )
                for a_idx, answer_data in enumerate(question_data.get('answers', [])):
                    is_correct = answer_data.get('option_key') == question_data.get('correct_answer_key')
                    GeneratedAnswer.objects.create(
                        question=question,
                        answer_text=answer_data.get('answer_text', f'Answer {a_idx+1}'),
                        option_key=answer_data.get('option_key', chr(65+a_idx)),
                        is_correct=is_correct,
                        order=a_idx
                    )
        
        # Log the regeneration - FIXED: Use student.pk instead of student.id
        logger.info(f"Regenerated topic {original_topic.id} for student {student.pk} with score {score_percentage}%")
        
        return regenerated_topic
        
    except Exception as e:
        logger.error(f"Error regenerating topic: {str(e)}")
        return None

def get_or_generate_next_topic(course, current_topic, student, score):
    """
    Get the next topic in sequence or generate a new one based on performance
    """
    try:
        # First, try to find the next topic in the existing sequence
        next_topic = GeneratedTopic.objects.filter(
            chapter__course=course,
            chapter__order__gte=current_topic.chapter.order,
            order__gt=current_topic.order
        ).order_by('chapter__order', 'order').first()
        
        if next_topic:
            return next_topic
        
        # If no next topic exists, we're at the end of the course
        # Check if we should generate additional topics based on performance
        if score < 70:  # If score is good but not excellent, generate reinforcement
            return generate_reinforcement_topic(course, current_topic, student, score)
        else:
            # For excellent scores, just return None (end of course)
            return None
            
    except Exception as e:
       
        return None


def generate_reinforcement_topic(course, current_topic, student, score):
    """
    Generate a reinforcement topic based on the student's performance
    """
    try:
        # Determine the focus area based on performance
        if score < 60:
            focus = "basic reinforcement"
        else:
            focus = "advanced practice"
        
        prompt = f"""
        Generate a follow-up C++ topic that reinforces the concepts from "{current_topic.title}".
        The student scored {score}% on the previous topic, so this should be {focus}.
        
        Create a topic that:
        1. Reviews key concepts from the previous topic
        2. Provides additional examples and practice
        3. Includes a quiz to assess understanding
        4. Is appropriate for someone who scored {score}%
        
        Respond with JSON in this format:
        {{
            "title": "Reinforcement Topic Title",
            "content": "Detailed content...",
            "description": "Brief description",
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
        """
        
        model = genai.GenerativeModel('gemini-2.0-flash-lite', generation_config={"response_mime_type": "application/json"})
        response = model.generate_content(prompt)
        topic_data = json.loads(response.text)
        
        # Create the new topic
        last_chapter = course.chapters.order_by('-order').first()
        new_chapter_order = last_chapter.order + 1 if last_chapter else 1
        
        # Create a new chapter for the reinforcement topic
        new_chapter = GeneratedChapter.objects.create(
            course=course,
            title=f"Reinforcement - {current_topic.title}",
            duration="15 min",
            order=new_chapter_order
        )
        
        # Create the reinforcement topic
        reinforcement_topic = GeneratedTopic.objects.create(
            chapter=new_chapter,
            title=topic_data.get('title', f"Reinforcement: {current_topic.title}"),
            content=topic_data.get('content', ''),
            description=topic_data.get('description', ''),
            order=0
        )
        
        # Create quiz if provided
        if 'quiz' in topic_data and topic_data['quiz'].get('questions'):
            quiz = GeneratedQuiz.objects.create(topic=reinforcement_topic)
            for q_idx, question_data in enumerate(topic_data['quiz']['questions']):
                question = GeneratedQuestion.objects.create(
                    quiz=quiz,
                    question_text=question_data.get('question_text', f'Question {q_idx+1}'),
                    order=q_idx
                )
                for a_idx, answer_data in enumerate(question_data.get('answers', [])):
                    is_correct = answer_data.get('option_key') == question_data.get('correct_answer_key')
                    GeneratedAnswer.objects.create(
                        question=question,
                        answer_text=answer_data.get('answer_text', f'Answer {a_idx+1}'),
                        option_key=answer_data.get('option_key', chr(65+a_idx)),
                        is_correct=is_correct,
                        order=a_idx
                    )
        
        return reinforcement_topic
        
    except Exception as e:
        
        return None


def get_remedial_resources(topic_name, learning_style):
    """Get remedial learning resources based on topic and learning style"""
    # This can be expanded with a database of resources
    resources = {
        'visual': [
            {'type': 'video', 'title': f'{topic_name} Visual Explanation', 'url': f'https://youtube.com/results?search_query={topic_name.replace(" ", "+")}+visual+explanation'},
            {'type': 'infographic', 'title': f'{topic_name} Infographic', 'url': f'https://google.com/search?q={topic_name.replace(" ", "+")}+infographic'}
        ],
        'auditory': [
            {'type': 'podcast', 'title': f'{topic_name} Podcast', 'url': f'https://google.com/search?q={topic_name.replace(" ", "+")}+podcast'},
            {'type': 'audio_lesson', 'title': f'{topic_name} Audio Lesson', 'url': f'https://youtube.com/results?search_query={topic_name.replace(" ", "+")}+audio+lesson'}
        ],
        'kinesthetic': [
            {'type': 'interactive_tutorial', 'title': f'{topic_name} Interactive Tutorial', 'url': f'https://google.com/search?q={topic_name.replace(" ", "+")}+interactive+tutorial'},
            {'type': 'practice_exercises', 'title': f'{topic_name} Practice Exercises', 'url': f'https://google.com/search?q={topic_name.replace(" ", "+")}+practice+exercises'}
        ]
    }
    
    return resources.get(learning_style, [
        {'type': 'general', 'title': f'Learn more about {topic_name}', 'url': f'https://google.com/search?q={topic_name.replace(" ", "+")}+tutorial'}
    ])
  
  
from django.core.exceptions import FieldError     
from django.db.models import Avg    
@login_required
def progress_analysis_view(request):
    """View for AI-powered progress analysis and recommendations"""
    student = request.user
    
    # Get progress data for regular courses
    regular_courses_progress = []
    courses = Course.objects.all()
    for course in courses:
        completed_lessons = UserProgress.objects.filter(
            student=student,
            lesson__module__course=course,
            is_completed=True
        ).count()
        total_lessons = sum(module.lessons.count() for module in course.modules.all())
        progress_percentage = int((completed_lessons / total_lessons) * 100) if total_lessons > 0 else 0
        
        regular_courses_progress.append({
            'course': course,
            'progress': progress_percentage,
            'completed': completed_lessons,
            'total': total_lessons
        })
    
    # Get progress data for generated courses
    generated_courses_progress = []
    generated_courses = GeneratedCourse.objects.filter(user=student)
    for course in generated_courses:
        completed_topics = GeneratedTopicCompletion.objects.filter(
            student=student,
            topic__chapter__course=course
        ).count()
        total_topics = GeneratedTopic.objects.filter(chapter__course=course).count()
        progress_percentage = int((completed_topics / total_topics) * 100) if total_topics > 0 else 0
        
        # Get average quiz scores - handle case where score field might not exist
        try:
            completions = GeneratedTopicCompletion.objects.filter(
                student=student,
                topic__chapter__course=course
            ).exclude(score=None)
            avg_score = completions.aggregate(Avg('score'))['score__avg'] or 0
        except FieldError:
            # Fallback if score field doesn't exist yet
            avg_score = 0
        
        generated_courses_progress.append({
            'course': course,
            'progress': progress_percentage,
            'completed': completed_topics,
            'total': total_topics,
            'avg_score': round(avg_score, 1)
        })
    
    # Prepare data for AI analysis
    progress_data = {
        'regular_courses': regular_courses_progress,
        'generated_courses': generated_courses_progress,
        'student_style': student.learning_style,
        'student_level': student.mastery_level
    }
    
    # Get AI recommendations
    ai_recommendations = get_ai_progress_recommendations(progress_data)
    
    context = {
        'regular_progress': regular_courses_progress,
        'generated_progress': generated_courses_progress,
        'ai_recommendations': ai_recommendations,
        'student': student
    }
    
    return render(request, 'progress_analysis.html', context)
def get_ai_progress_recommendations(progress_data):
    """Get AI-powered recommendations based on student progress"""
    try:
        # Prepare prompt for Gemini AI
        prompt = f"""
        Analyze this student's learning progress and provide personalized recommendations:
        
        Student Profile:
        - Learning Style: {progress_data['student_style']}
        - Mastery Level: {progress_data['student_level']}
        
        
        
        AI-Generated Courses Progress:
        {json.dumps([{'course': c['course'].title, 'progress': c['progress'], 'avg_score': c['avg_score']} for c in progress_data['generated_courses']], indent=2)}
        
        Please provide:
        1. A brief analysis of the student's overall progress
        2. Identification of strengths and weaknesses
        3. 3-5 personalized recommendations for what to study next
        4. Suggestions tailored to their learning style
        5. Encouragement based on their progress
        
        Format the response as a JSON object with: analysis, strengths, weaknesses, recommendations, and encouragement.
        """
        
        # Call Gemini AI
        model = genai.GenerativeModel('gemini-2.0-flash-lite')
        response = model.generate_content(prompt)
        
        # Parse the AI response
        if response.text:
            # Clean the response (remove markdown code blocks if present)
            clean_response = response.text.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response.removeprefix('```json').removesuffix('```').strip()
            
            return json.loads(clean_response)
        
    except Exception as e:
        print(f"Error getting AI recommendations: {e}")
    
    # Fallback recommendations if AI fails
    return {
        "analysis": "We're having trouble analyzing your progress right now.",
        "strengths": [],
        "weaknesses": [],
        "recommendations": [
            "Continue with your current learning path",
            "Review topics where you scored lower",
            "Try mixing different types of content"
        ],
        "encouragement": "Keep up the good work! Consistent learning leads to mastery."
    }     
    
from .models import CppLearningResource    
def generate_simplified_content(original_content, score):
    """Generate a simplified version of the content based on the user's score"""
    # The lower the score, the more basic the content should be
    if score < 20:
        complexity_level = "very basic"
    elif score < 35:
        complexity_level = "basic"
    else:
        complexity_level = "simplified"
    
    prompt = f"""
    Rewrite the following C++ educational content at a {complexity_level} level. 
    Use simpler language, more examples, and break down complex concepts.
    
    Original Content:
    {original_content}
    
    Respond with only the simplified content, no additional commentary.
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        # Fallback: return the original content if AI generation fails
        return original_content

def get_cpp_remedial_resources(topic_name, score_percentage, wrong_answers=None):
    """Get AI-generated specific C++ learning resources based on topic, performance, and wrong answers"""
    try:
        # Build prompt with wrong answers context if available
        wrong_answers_context = ""
        if wrong_answers:
            wrong_answers_context = "\n\nThe student specifically struggled with these questions:\n"
            for i, wrong in enumerate(wrong_answers, 1):
                # Make sure we're using the correct field names
                question_text = wrong.get('question', wrong.get('question_text', 'Unknown question'))
                user_answer = wrong.get('user_answer', 'No answer')
                correct_answer = wrong.get('correct_answer', wrong.get('correct_answer_text', 'Unknown answer'))
                
                wrong_answers_context += f"{i}. Question: {question_text}\n"
                wrong_answers_context += f"   Their answer: {user_answer}\n"
                wrong_answers_context += f"   Correct answer: {correct_answer}\n"
        
        prompt = f"""
        A student scored {score_percentage}% on a C++ quiz about "{topic_name}".{wrong_answers_context}
        
        They need additional learning resources to improve their understanding, particularly focusing on the areas where they struggled.
        
        Please recommend 3-5 specific, high-quality C++ learning resources that would help them. For each resource, provide:
        1. Exact title of the resource
        2. Specific URL to the relevant content
        3. Type (video, article, tutorial, exercises, documentation)
        4. Source (freeCodeCamp, W3Schools, GeeksforGeeks, LearnCpp, cppreference, etc.)
        5. Brief description of why this resource would help address their specific misunderstandings
        
        Focus on resources that are:
        - Specifically about C++ (not general programming)
        - From reputable sources
        - Appropriate for someone who scored {score_percentage}%
        - Directly relevant to "{topic_name}" and the specific concepts they struggled with
        
        Return the response as a JSON array of objects with these fields:
        title, url, type, source, description
        
        Example:
        [
            {{
                "title": "C++ Pointers Explained",
                "url": "https://www.youtube.com/watch?v=DTxHyVn0ODg",
                "type": "video",
                "source": "freeCodeCamp",
                "description": "Comprehensive video explaining pointers with visual examples, which addresses the student's confusion about pointer arithmetic"
            }}
        ]
        """
        
        model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})
        response = model.generate_content(prompt)
        
        # Parse the AI response
        ai_resources = json.loads(response.text)
        
        # Validate and format the resources
        formatted_resources = []
        for resource in ai_resources:
            if all(key in resource for key in ['title', 'url', 'type', 'source', 'description']):
                formatted_resources.append({
                    'title': resource['title'],
                    'url': resource['url'],
                    'type': resource['type'],
                    'source': resource['source'],
                    'description': resource['description']
                })
        
        return formatted_resources[:5]  # Return max 5 resources
        
    except Exception as e:
        # Fallback to curated resources if AI fails
        logger.error(f"AI resource generation failed: {str(e)}")
        return get_curated_cpp_resources(topic_name, score_percentage)

def get_curated_cpp_resources(topic_name, score_percentage):
    """Curated fallback resources when AI generation fails"""
    # Map topics to specific resources
    topic_resources = {
        'pointer': [
            {
                'title': 'Pointers in C++',
                'url': 'https://www.learncpp.com/cpp-tutorial/pointers/',
                'type': 'tutorial',
                'source': 'LearnCpp',
                'description': 'Comprehensive tutorial on C++ pointers with examples'
            },
            {
                'title': 'C++ Pointers Explained',
                'url': 'https://www.youtube.com/watch?v=DTxHyVn0ODg',
                'type': 'video',
                'source': 'freeCodeCamp',
                'description': 'Visual explanation of pointers in C++'
            }
        ],
        'class': [
            {
                'title': 'C++ Classes and Objects',
                'url': 'https://www.w3schools.com/cpp/cpp_classes.asp',
                'type': 'tutorial',
                'source': 'W3Schools',
                'description': 'Interactive tutorial on classes and objects'
            },
            {
                'title': 'C++ OOP Tutorial',
                'url': 'https://www.youtube.com/watch?v=wN0x9eZLix4',
                'type': 'video',
                'source': 'freeCodeCamp',
                'description': 'Complete OOP tutorial for beginners'
            }
        ],
        'inheritance': [
            {
                'title': 'Inheritance in C++',
                'url': 'https://www.learncpp.com/cpp-tutorial/basic-inheritance-in-c/',
                'type': 'tutorial',
                'source': 'LearnCpp',
                'description': 'Detailed guide to inheritance concepts'
            }
        ],
        'template': [
            {
                'title': 'C++ Templates',
                'url': 'https://www.geeksforgeeks.org/templates-cpp/',
                'type': 'tutorial',
                'source': 'GeeksforGeeks',
                'description': 'Comprehensive template tutorial with examples'
            }
        ],
        'vector': [
            {
                'title': 'C++ Vector Tutorial',
                'url': 'https://www.cplusplus.com/reference/vector/vector/',
                'type': 'documentation',
                'source': 'cplusplus.com',
                'description': 'Official vector documentation with examples'
            }
        ]
    }
    
    # Find resources for the specific topic
    topic_lower = topic_name.lower()
    resources = []
    
    for keyword, resource_list in topic_resources.items():
        if keyword in topic_lower:
            resources.extend(resource_list)
    
    # If no specific topic resources found, provide general C++ resources
    if not resources:
        resources = [
            {
                'title': 'C++ Tutorial for Beginners',
                'url': 'https://www.learncpp.com/',
                'type': 'tutorial',
                'source': 'LearnCpp',
                'description': 'Complete C++ tutorial from basics to advanced'
            },
            {
                'title': 'C++ Programming Course',
                'url': 'https://www.youtube.com/watch?v=vLnPwxZdW4Y',
                'type': 'video',
                'source': 'freeCodeCamp',
                'description': 'Full C++ programming course for beginners'
            },
            {
                'title': 'C++ Reference',
                'url': 'https://en.cppreference.com/w/',
                'type': 'documentation',
                'source': 'cppreference',
                'description': 'Comprehensive C++ language reference'
            }
        ]
    
    return resources[:3]  # Return max 3 curated resources
def generate_ai_feedback(topic, user_answers, score, passed, remedial_resources):
    """Generate personalized AI feedback based on performance"""
    performance_data = []
    total_questions = topic.quiz.questions.count() if hasattr(topic, 'quiz') else 0
    
    # Collect wrong answers for more specific feedback
    wrong_answers = []
    if total_questions > 0:
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
            
            if not is_correct:
                wrong_answers.append({
                    'question': question.question_text,
                    'correct_answer': correct_answer.answer_text,
                    'user_answer': user_selected_option
                })
    
    # Format remedial resources for the prompt
    resource_list = "\n".join([f"- {r['title']} ({r['source']}): {r['url']}" for r in remedial_resources])
    
    # Include wrong answers in the prompt for more specific feedback
    wrong_answers_context = ""
    if wrong_answers:
        wrong_answers_context = "\nAreas needing improvement:\n"
        for i, wrong in enumerate(wrong_answers, 1):
            wrong_answers_context += f"{i}. {wrong['question']}\n"
            wrong_answers_context += f"   Your answer: {wrong['user_answer']}\n"
            wrong_answers_context += f"   Correct answer: {wrong['correct_answer']}\n"
    
    prompt = f"""
    Analyze the student's quiz performance on the topic "{topic.title}" and provide personalized feedback.
    The student scored {score}% and {'passed' if passed else 'did not pass'}.{wrong_answers_context}
    
    Recommended resources:
    {resource_list}
    
    Provide feedback that:
    1. Starts with an encouraging tone
    2. Highlights what they did well
    3. Explains key areas for improvement based on their wrong answers
    4. Recommends specific resources to review based on their mistakes
    5. Ends with motivational closing
    
    Keep the response under 250 words.
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-lite')
        ai_response = model.generate_content(prompt)
        return ai_response.text
    except Exception as e:
        logger.error(f"AI feedback generation failed: {str(e)}")
        # Fallback feedback
        if passed:
            return f"Great job! You scored {score}% and passed this quiz on {topic.title}."
        else:
            return f"You scored {score}% on {topic.title}. Review the material and try again. Recommended resources: {', '.join([r['title'] for r in remedial_resources])}"

@require_POST
@login_required
@csrf_protect
def regenerate_topic(request):
    """API endpoint to regenerate a simpler version of a topic"""
    try:
        data = json.loads(request.body)
        course_id = data.get('course_id')
        topic_id = data.get('topic_id')
        
        if not course_id or not topic_id:
            return JsonResponse({'success': False, 'error': 'Course ID and Topic ID are required.'}, status=400)
            
        course = get_object_or_404(GeneratedCourse, id=course_id, user=request.user)
        topic = get_object_or_404(GeneratedTopic, id=topic_id, chapter__course=course)
        
        # Prevent regenerating from a regenerated topic
        if topic.is_regenerated:
            return JsonResponse({
                'success': False, 
                'error': 'Cannot generate a simplified lesson from an already simplified lesson.'
            }, status=400)
        
        # Check if the student has already completed this topic
        try:
            completion = GeneratedTopicCompletion.objects.get(student=request.user, topic=topic)
            score_percentage = completion.score
        except GeneratedTopicCompletion.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'You must complete the topic first.'}, status=400)
        
        # Only allow regeneration if the student failed
        if score_percentage >= 50:
            return JsonResponse({'success': False, 'error': 'You passed this topic. Regeneration is only available if you failed.'}, status=400)
        
        # Check if a regenerated topic already exists for this student and original topic
        existing_regenerated = GeneratedTopic.objects.filter(
            original_topic=topic, 
            chapter__course=course,
            is_regenerated=True
        ).first()
        
        if existing_regenerated:
            return JsonResponse({
                'success': True, 
                'regenerated_topic_id': existing_regenerated.id,
                'message': 'A simplified version already exists.'
            })
        
        # Get wrong answers from the completion record if available
        wrong_answers = []
        if hasattr(completion, 'wrong_answers') and completion.wrong_answers:
            wrong_answers = completion.wrong_answers
        
        # Regenerate a simpler topic
        regenerated_topic = regenerate_simpler_topic(topic, request.user, score_percentage, wrong_answers)
        
        if regenerated_topic:
            return JsonResponse({
                'success': True, 
                'regenerated_topic_id': regenerated_topic.id,
                'message': 'Simplified topic generated successfully.'
            })
        else:
            return JsonResponse({'success': False, 'error': 'Failed to generate simplified topic.'}, status=500)
            
    except Exception as e:
        logger.error(f"Error in regenerate_topic: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Internal server error.'}, status=500)