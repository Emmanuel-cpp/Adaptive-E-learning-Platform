# content/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
import time

from django.http import JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST
from django.conf import settings
from django.db.models import Q
from django.db import transaction
from .models import Course, Module, Lesson, GeneratedCourse, GeneratedChapter, GeneratedTopic, GeneratedQuiz, GeneratedQuestion, GeneratedAnswer, GeneratedCourseProgress, GeneratedTopicCompletion
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
def learning_view(request):
    generated_course_id = request.GET.get('generated_course_id')
    topic_id = request.GET.get('topic_id')
    
    context = {}
    
    # Handle generated courses
    if generated_course_id and topic_id:
        try:
            course = get_object_or_404(GeneratedCourse, id=generated_course_id, user=request.user)
            topic = get_object_or_404(GeneratedTopic, id=topic_id, chapter__course=course)
            chapter = topic.chapter
            
            # Get all topics in the course (single chapter)
            all_topics = GeneratedTopic.objects.filter(chapter__course=course).order_by('order')
            
            # Find current topic position
            topic_index = None
            for idx, t in enumerate(all_topics):
                if t.id == topic.id:
                    topic_index = idx
                    break
            
            # Get previous and next topics
            previous_topic = None
            next_topic = None
            
            if topic_index is not None:
                if topic_index > 0:
                    previous_topic = all_topics[topic_index - 1]
                
                if topic_index < len(all_topics) - 1:
                    next_topic = all_topics[topic_index + 1]
            
            # Check if topic is completed
            topic_completed = False
            completion = None
            try:
                completion = GeneratedTopicCompletion.objects.get(student=request.user, topic=topic)
                topic_completed = True
                context['completion'] = completion
            except GeneratedTopicCompletion.DoesNotExist:
                pass
            
            # Get quiz questions if available
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
            
            # Update or create course progress
            progress, created = GeneratedCourseProgress.objects.get_or_create(
                student=request.user,
                course=course,
                defaults={'last_accessed_topic': topic}
            )
            if not created:
                progress.last_accessed_topic = topic
                progress.save()
            
            # Calculate progress percentage as a whole number
            total_topics = GeneratedTopic.objects.filter(chapter__course=course).count()
            completed_topics = GeneratedTopicCompletion.objects.filter(
                student=request.user, 
                topic__chapter__course=course,
                score__gte=50  # Only count topics passed with 50% or higher
            ).count()
            
            # Calculate percentage and convert to integer (whole number)
            if total_topics > 0:
                progress_percentage = int((completed_topics / total_topics) * 100)
            else:
                progress_percentage = 0
            
            # Check if this is a regenerated topic
            original_topic = None
            if topic.is_regenerated and hasattr(topic, 'original_topic'):
                original_topic = topic.original_topic
            
            # Check if this topic needs a reinforcement lesson
            needs_reinforcement = False
            reinforcement_topic = None
            
            # If this is the last topic in the course and student has completed all topics
            if topic_index == len(all_topics) - 1 and topic_completed:
                # Check if student passed all topics in this course
                all_passed = True
                for course_topic in all_topics:
                    try:
                        topic_comp = GeneratedTopicCompletion.objects.get(
                            student=request.user, 
                            topic=course_topic
                        )
                        if topic_comp.score < 50:
                            all_passed = False
                            break
                    except GeneratedTopicCompletion.DoesNotExist:
                        all_passed = False
                        break
                
                # If student didn't pass all topics, they need reinforcement
                if not all_passed:
                    needs_reinforcement = True
                    
                    # Check if reinforcement topic already exists
                    reinforcement_topic = GeneratedTopic.objects.filter(
                        chapter__course=course,
                        is_reinforcement=True
                    ).first()
                    
                    # If no reinforcement topic exists, create one
                    if not reinforcement_topic:
                        reinforcement_topic = create_reinforcement_topic(course, request.user)
            
            # Determine which topics are unlocked
            unlocked_topics = []
            for idx, t in enumerate(all_topics):
                # First topic is always unlocked
                if idx == 0:
                    unlocked_topics.append(t.id)
                    continue
                
                # Check if previous topic is completed
                prev_topic = all_topics[idx - 1]
                try:
                    comp = GeneratedTopicCompletion.objects.get(
                        student=request.user, 
                        topic=prev_topic
                    )
                    if comp.score >= 50:  # Passed
                        unlocked_topics.append(t.id)
                except GeneratedTopicCompletion.DoesNotExist:
                    # Previous topic not completed
                    pass
            
            # Check if user is trying to access a locked topic
            if topic.id not in unlocked_topics:
                # Find the first incomplete topic
                first_incomplete_topic = None
                for t in all_topics:
                    if t.id in unlocked_topics:
                        try:
                            completion = GeneratedTopicCompletion.objects.get(student=request.user, topic=t)
                            if completion.score < 50:  # Not passed
                                first_incomplete_topic = t
                                break
                        except GeneratedTopicCompletion.DoesNotExist:
                            first_incomplete_topic = t
                            break
                
                if first_incomplete_topic:
                    return redirect(f'/learning/?generated_course_id={course.id}&topic_id={first_incomplete_topic.id}')
                else:
                    # This shouldn't happen, but fallback to first topic
                    first_topic = all_topics.first()
                    if first_topic:
                        return redirect(f'/learning/?generated_course_id={course.id}&topic_id={first_topic.id}')
                
                return redirect('dashboard')
            
            context.update({
                'course': course,
                'module': chapter,
                'lesson': topic,
                'original_topic': original_topic,
                'progress_percentage': progress_percentage,
                'previous_lesson': previous_topic,
                'next_lesson': next_topic,
                'is_generated': True,
                'quiz_questions': quiz_questions,
                'topic_completed': topic_completed,
                'is_regenerated': topic.is_regenerated if hasattr(topic, 'is_regenerated') else False,
                'needs_reinforcement': needs_reinforcement,
                'reinforcement_topic': reinforcement_topic,
                'unlocked_topics': unlocked_topics,
                'all_topics': all_topics,
            })
            
            return render(request, 'learning.html', context)
            
        except Exception as e:
            logger.error(f"Error in learning_view for generated course: {str(e)}")
            return redirect('dashboard')
    
    # Invalid parameters
    return redirect('dashboard')

        
@require_POST
@login_required
@csrf_protect
def generate_course(request):
    try:
        data = json.loads(request.body)
        original_title = data.get('name')
        level = data.get('level')
        lessons = data.get('lessons', [])
        no_of_chapters = 1

        if not original_title or not level:
            return JsonResponse({'success': False, 'error': 'Course name and level are required'}, status=400)

        # Generate a unique course title
        base_title = original_title
        counter = 1
        while True:
            if not GeneratedCourse.objects.filter(user=request.user, title=base_title).exists():
                break
            base_title = f"{original_title} ({counter})"
            counter += 1

        # Create the course with the unique title
        course = GeneratedCourse.objects.create(
            user=request.user,
            title=base_title,
            description=f"AI-generated C++ course for {level} level",
            level=level,
            chapters_count=no_of_chapters,
            category="C++ Programming"
        )

        # Revised lessons with memory management moved to moderate level
        if not lessons:
            lessons_map = {
                'beginner': [
                    "Introduction to C++ Programming",
                    "Variables, Data Types, and Constants",
                    "Basic Input/Output Operations",
                    "Control Flow and Functions",
                    "Arrays and Strings",
                    "Setting Up Development Environment"
                ],
                'moderate': [
                    "Object-Oriented Programming Concepts",
                    "Basic Memory Management",  # Moved from beginner to moderate
                    "Advanced Pointers and Memory",
                    "Inheritance and Polymorphism",
                    "Exception Handling",
                    "File I/O Operations"
                ],
                'advanced': [
                    "Advanced Memory Management",
                    "Multithreading and Concurrency",
                    "Template Metaprogramming",
                    "STL Containers and Algorithms",
                    "Performance Optimization",
                    "Design Patterns in C++"
                ]
            }
            lessons = lessons_map.get(level, lessons_map['beginner'])

        # Enhanced AI Prompt for comprehensive content with strict quiz requirements
        prompt = f"""
        CRITICAL INSTRUCTION: You MUST create a comprehensive C++ course with detailed lessons. 
        EVERY SINGLE LESSON MUST include a quiz with exactly 4 high-quality questions.
        The quiz is ESSENTIAL for student progression in the learning system.
        
        COURSE TITLE: "{base_title}"
        TARGET AUDIENCE: {level} level C++ students
        LESSON COUNT: {len(lessons)}
        
        NON-NEGOTIABLE REQUIREMENTS:
        1. Each lesson MUST have a quiz with exactly 4 questions
        2. Each question MUST have exactly 4 answer options (A, B, C, D)
        3. Only one correct answer per question
        4. Questions must test actual understanding of the lesson content
        5. Answer options must be plausible but only one is correct
        6. Lesson content must be comprehensive (1000+ words) with code examples
        
        LESSONS TO CREATE (in exact order):
        {json.dumps(lessons, indent=2)}
        
        FORMAT REQUIREMENTS:
        You MUST return valid JSON with this exact structure:
        {{
            "lessons": [
                {{
                    "title": "Exact lesson title from the list above",
                    "order": 1,
                    "content": "Comprehensive lesson content (1000+ words) with:
                    - Clear explanations of concepts
                    - Practical code examples
                    - Real-world applications
                    - Best practices
                    - Common pitfalls to avoid
                    - Memory diagrams where appropriate",
                    "quiz": {{
                        "questions": [
                            {{
                                "question_text": "Challenging question that tests understanding",
                                "answers": [
                                    {{"answer_text": "Plausible but incorrect option", "option_key": "A", "is_correct": false}},
                                    {{"answer_text": "Correct answer", "option_key": "B", "is_correct": true}},
                                    {{"answer_text": "Plausible but incorrect option", "option_key": "C", "is_correct": false}},
                                    {{"answer_text": "Clearly wrong option", "option_key": "D", "is_correct": false}}
                                ]
                            }},
                            {{
                                "question_text": "Question about practical application",
                                "answers": [
                                    {{"answer_text": "Partially correct but incomplete", "option_key": "A", "is_correct": false}},
                                    {{"answer_text": "Correct application", "option_key": "B", "is_correct": true}},
                                    {{"answer_text": "Completely wrong approach", "option_key": "C", "is_correct": false}},
                                    {{"answer_text": "Opposite of correct approach", "option_key": "D", "is_correct": false}}
                                ]
                            }},
                            {{
                                "question_text": "Question about syntax or code structure",
                                "answers": [
                                    {{"answer_text": "Incorrect syntax", "option_key": "A", "is_correct": false}},
                                    {{"answer_text": "Correct syntax", "option_key": "B", "is_correct": true}},
                                    {{"answer_text": "Invalid approach", "option_key": "C", "is_correct": false}},
                                    {{"answer_text": "Working but inefficient approach", "option_key": "D", "is_correct": false}}
                                ]
                            }},
                            {{
                                "question_text": "Conceptual question about underlying principles",
                                "answers": [
                                    {{"answer_text": "Misunderstanding of concept", "option_key": "A", "is_correct": false}},
                                    {{"answer_text": "Accurate understanding", "option_key": "B", "is_correct": true}},
                                    {{"answer_text": "Common misconception", "option_key": "C", "is_correct": false}},
                                    {{"answer_text": "Irrelevant information", "option_key": "D", "is_correct": false}}
                                ]
                            }}
                        ]
                    }}
                }}
            ]
        }}
        
        FAILURE TO INCLUDE A QUIZ FOR ANY LESSON WILL MAKE THE ENTIRE COURSE USELESS.
        STUDENTS CANNOT PROGRESS WITHOUT COMPLETING QUIZZES.
        THIS IS THE MOST IMPORTANT REQUIREMENT.
        
        TONE AND STYLE:
        - Professional but accessible for {level} level students
        - Practical with real code examples
        - Focus on understanding rather than memorization
        - Include both theoretical concepts and practical applications
        
        REMEMBER: QUIZZES ARE NOT OPTIONAL. THEY ARE REQUIRED FOR EVERY LESSON.
        """

        logger.info(f"Sending enhanced prompt to AI: {prompt[:500]}")

        # AI Generation with strict validation
        max_retries = 5  # Increased retries for better chance of success
        retry_delay = 2
        course_data = None
        
        for attempt in range(max_retries):
            try:
                model = genai.GenerativeModel('gemini-2.5-flash-lite', generation_config={"response_mime_type": "application/json"})
                response = model.generate_content(prompt)
                logger.info(f"AI response received (first 500 chars): {response.text[:500]}")

                # Try parsing JSON
                try:
                    course_data = json.loads(response.text)
                except json.JSONDecodeError:
                    cleaned = response.text.strip()
                    cleaned = re.sub(r'^```json', '', cleaned)
                    cleaned = re.sub(r'```$', '', cleaned)
                    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                    if match:
                        course_data = json.loads(match.group())
                    else:
                        raise ValueError("Could not extract JSON from response")

                if 'lessons' not in course_data:
                    raise ValueError("AI response missing 'lessons' key")
                
                # Validate that each lesson has a quiz with exactly 4 questions
                valid_lessons = True
                missing_quizzes = []
                
                for i, lesson in enumerate(course_data.get('lessons', [])):
                    lesson_title = lesson.get('title', f'Lesson {i+1}')
                    
                    if 'quiz' not in lesson:
                        missing_quizzes.append(lesson_title)
                        valid_lessons = False
                        continue
                    
                    questions = lesson['quiz'].get('questions', [])
                    if len(questions) < 4:
                        missing_quizzes.append(f"{lesson_title} (only {len(questions)} questions)")
                        valid_lessons = False
                    elif len(questions) > 4:
                        # If more than 4 questions, just take the first 4
                        lesson['quiz']['questions'] = questions[:4]
                
                if valid_lessons:
                    logger.info("All lessons have valid quizzes")
                    break
                else:
                    error_msg = f"Missing or incomplete quizzes for: {', '.join(missing_quizzes)}"
                    logger.warning(f"Attempt {attempt+1} failed: {error_msg}")
                    
                    if attempt < max_retries - 1:
                        # Add specific feedback to the prompt for the next attempt
                        prompt += f"\n\nPREVIOUS ATTEMPT FAILED: The following lessons were missing quizzes: {', '.join(missing_quizzes)}. PLEASE ENSURE every lesson has a complete quiz with exactly 4 questions."
                        time.sleep(retry_delay)
                    else:
                        raise ValueError(error_msg)
                    
            except Exception as e:
                logger.error(f"AI generation failed attempt {attempt+1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                else:
                    course.delete()
                    return JsonResponse({
                        'success': False,
                        'error': f'AI generation failed: {str(e)}'
                    }, status=500)

        # Create Chapter
        chapter = GeneratedChapter.objects.create(
            course=course,
            title="Main Lessons",
            order=1,
            duration="N/A",
            image_prompt=""
        )

        # Create Lessons & Quizzes
        first_topic_id = None
        for lesson_data in course_data.get('lessons', []):
            topic = GeneratedTopic.objects.create(
                chapter=chapter,
                title=lesson_data.get('title', 'Untitled Lesson'),
                content=lesson_data.get('content', ''),
                order=lesson_data.get('order', 1),
                is_regenerated=False,
                is_reinforcement=False
            )

            if first_topic_id is None:
                first_topic_id = topic.id

            # Create quiz - ensure we have exactly 4 questions
            quiz_data = lesson_data.get('quiz', {})
            quiz = GeneratedQuiz.objects.create(topic=topic)
            
            # Create questions and answers
            questions = quiz_data.get('questions', [])
            for q_idx, question_data in enumerate(questions[:4]):  # Limit to 4 questions
                question = GeneratedQuestion.objects.create(
                    quiz=quiz,
                    question_text=question_data.get('question_text', f'Question {q_idx+1}'),
                    order=q_idx
                )
                
                # Create answers
                answers = question_data.get('answers', [])
                for a_idx, answer_data in enumerate(answers[:4]):  # Limit to 4 answers
                    GeneratedAnswer.objects.create(
                        question=question,
                        answer_text=answer_data.get('answer_text', f'Answer {a_idx+1}'),
                        option_key=answer_data.get('option_key', chr(65 + a_idx)),
                        is_correct=answer_data.get('is_correct', False),
                        order=a_idx
                    )

        logger.info(f"Course generated successfully: {course.id}, first topic: {first_topic_id}")
        return JsonResponse({
            'success': True,
            'course_id': course.id,
            'first_topic_id': first_topic_id,
            'message': 'Course generated successfully'
        })

    except Exception as e:
        logger.error(f"Error in generate_course: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

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
        is_retry = data.get('is_retry', False)

        if not topic_id:
            return JsonResponse({'success': False, 'error': 'Topic ID is required.'}, status=400)

        topic = get_object_or_404(GeneratedTopic, id=topic_id)
        student = request.user
        course = topic.chapter.course
        
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
        
        # Check if student passed (50% or higher)
        passed = score_percentage >= 50
        
        # Get or create completion record
        try:
            completion = GeneratedTopicCompletion.objects.get(student=student, topic=topic)
            # Update existing record
            completion.score = score_percentage
            completion.passed = passed
            completion.attempt_count += 1  # Manual increment
            completion.save()
        except GeneratedTopicCompletion.DoesNotExist:
            # Create new record
            completion = GeneratedTopicCompletion.objects.create(
                student=student,
                topic=topic,
                score=score_percentage,
                passed=passed,
                attempt_count=1
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
        remedial_resources = get_cpp_remedial_resources(topic.title, score_percentage)
        
        # Generate AI feedback
        ai_feedback = generate_ai_feedback(topic, user_answers, score_percentage, passed, remedial_resources)

        # Find next topic based on performance
        next_topic = None
        if passed:
            # Find next topic in sequence
            all_topics = GeneratedTopic.objects.filter(chapter__course=course).order_by('order')
            current_index = None
            for idx, t in enumerate(all_topics):
                if t.id == topic.id:
                    current_index = idx
                    break
            
            if current_index is not None and current_index < len(all_topics) - 1:
                next_topic = all_topics[current_index + 1]
                
                # If performance was poor, adapt the next topic
                if score_percentage < 70:
                    next_topic = generate_adapted_topic(next_topic, score_percentage)
        
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

    
def generate_adapted_topic(original_topic, performance_score):
    """Generate an adapted version of a topic based on performance"""
    try:
        # Determine complexity level based on performance
        if performance_score < 50:
            complexity = "very basic"
        elif performance_score < 70:
            complexity = "basic"
        else:
            return original_topic  # No adaptation needed
        
        prompt = f"""
        Create a {complexity} version of the following C++ lesson for a student who scored {performance_score}% on the previous lesson.
        
        Original Lesson: {original_topic.title}
        Original Content: {original_topic.content[:1000]}...
        
        Please create a simplified version that:
        1. Uses simpler language and more examples
        2. Focuses on core concepts
        3. Breaks down complex ideas into smaller steps
        4. Includes practical examples
        
        Respond with JSON containing:
        - title: Adapted title
        - content: Simplified content
        - quiz: Simplified quiz with 3 questions
        """
        
        # Generate content using AI
        model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})
        response = model.generate_content(prompt)
        
        # Parse and create adapted topic
        adapted_data = json.loads(response.text)
        
        # Create adapted topic
        adapted_topic = GeneratedTopic.objects.create(
            chapter=original_topic.chapter,
            title=adapted_data.get('title', f"Simplified: {original_topic.title}"),
            content=adapted_data.get('content', ''),
            order=original_topic.order,
            is_regenerated=True,
            original_topic=original_topic
        )
        
        # Create adapted quiz if provided
        if 'quiz' in adapted_data:
            quiz = GeneratedQuiz.objects.create(topic=adapted_topic)
            
            for q_idx, question_data in enumerate(adapted_data['quiz'].get('questions', [])):
                question = GeneratedQuestion.objects.create(
                    quiz=quiz,
                    question_text=question_data.get('question_text', f'Question {q_idx+1}'),
                    order=q_idx
                )
                
                for a_idx, answer_data in enumerate(question_data.get('answers', [])):
                    GeneratedAnswer.objects.create(
                        question=question,
                        answer_text=answer_data.get('answer_text', f'Answer {a_idx+1}'),
                        option_key=answer_data.get('option_key', chr(65 + a_idx)),
                        is_correct=answer_data.get('is_correct', False),
                        order=a_idx
                    )
        
        return adapted_topic
        
    except Exception as e:
        logger.error(f"Error generating adapted topic: {str(e)}")
        return original_topic  # Fallback to original
    
    
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
        1. A brief analysis of the student's overall progress, if they have performed bad tell them it is not good and need improvement
        2. Identification of strengths and weaknesses
        3. 3-5 personalized recommendations for what to study next
        4. Suggestions tailored to their learning style
        5. Encouragement based on their progress
        
        Format the response as a JSON object with: analysis, strengths, weaknesses, recommendations, and encouragement.
        """
        
        # Call Gemini AI
        model = genai.GenerativeModel('gemini-2.5-flash')
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
                4. Source (only from reputable, well-known platforms such as freeCodeCamp, W3Schools, GeeksforGeeks, LearnCpp, cppreference, Programiz, The Cherno, or other highly rated C++ resources)
                5. Brief description of why this resource would help address their specific misunderstandings

                Focus on resources that are:
                - Specifically about C++ (not general programming)
                - From **trusted, reputable, and widely recognized sources**
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
    1. Starts with an encouraging tone, start with whether they did good or bad
    2. Highlights what they did well
    3. Explains key areas for improvement based on their wrong answers
    4. Recommends specific resources to review based on their mistakes
    5. Ends with motivational closing
    
    Keep the response under 250 words.
    """
    
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
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
        logger.info("Regenerate topic endpoint called by user: %s", request.user.username)
        data = json.loads(request.body)
        course_id = data.get('course_id')
        topic_id = data.get('topic_id')
        
        logger.info("Request data: course_id=%s, topic_id=%s", course_id, topic_id)
        
        if not course_id or not topic_id:
            error_msg = 'Course ID and Topic ID are required.'
            logger.error(error_msg)
            return JsonResponse({'success': False, 'error': error_msg}, status=400)
        
        course = get_object_or_404(GeneratedCourse, id=course_id, user=request.user)
        topic = get_object_or_404(GeneratedTopic, id=topic_id, chapter__course=course)
        
        logger.info("Found course: %s and topic: %s", course.title, topic.title)
        
        # Prevent regenerating from a regenerated topic
        if topic.is_regenerated:
            error_msg = 'Cannot generate a simplified lesson from an already simplified lesson.'
            logger.error(error_msg)
            return JsonResponse({'success': False, 'error': error_msg}, status=400)
        
        # Check if the student has already completed this topic
        try:
            completion = GeneratedTopicCompletion.objects.get(student=request.user, topic=topic)
            score_percentage = completion.score
            logger.info("Topic completion found with score: %s", score_percentage)
        except GeneratedTopicCompletion.DoesNotExist:
            error_msg = 'You must complete the topic first.'
            logger.error(error_msg)
            return JsonResponse({'success': False, 'error': error_msg}, status=400)
        
        # Only allow regeneration if the student failed
        if score_percentage >= 50:
            error_msg = 'You passed this topic. Regeneration is only available if you failed.'
            logger.error(error_msg)
            return JsonResponse({'success': False, 'error': error_msg}, status=400)
        
        # Check if a regenerated topic already exists for this student and original topic
        existing_regenerated = GeneratedTopic.objects.filter(
            original_topic=topic, 
            chapter__course=course,
            is_regenerated=True
        ).first()
        
        if existing_regenerated:
            # Check if student has already completed the regenerated topic
            try:
                regen_completion = GeneratedTopicCompletion.objects.get(
                    student=request.user, 
                    topic=existing_regenerated
                )
                # If completed, check if they passed
                if regen_completion.score >= 50:
                    return JsonResponse({
                        'success': False, 
                        'error': 'You have already completed a simplified version of this topic and passed.'
                    })
                else:
                    # If they failed the regenerated topic, allow retrying it
                    return JsonResponse({
                        'success': True, 
                        'regenerated_topic_id': existing_regenerated.id,
                        'message': 'A simplified version already exists.'
                    })
            except GeneratedTopicCompletion.DoesNotExist:
                # Regenerated topic exists but not completed
                return JsonResponse({
                    'success': True, 
                    'regenerated_topic_id': existing_regenerated.id,
                    'message': 'A simplified version already exists.'
                })
        
        # Get wrong answers from the completion record if available
        wrong_answers = []
        if hasattr(completion, 'wrong_answers') and completion.wrong_answers:
            wrong_answers = completion.wrong_answers
            logger.info("Found %s wrong answers", len(wrong_answers))
        
        # Regenerate a simpler topic
        regenerated_topic = regenerate_simpler_topic(topic, request.user, score_percentage, wrong_answers)
        
        if regenerated_topic:
            logger.info("Successfully regenerated topic with ID: %s", regenerated_topic.id)
            return JsonResponse({
                'success': True, 
                'regenerated_topic_id': regenerated_topic.id,
                'message': 'Simplified topic generated successfully.'
            })
        else:
            error_msg = 'Failed to generate simplified topic.'
            logger.error(error_msg)
            return JsonResponse({'success': False, 'error': error_msg}, status=500)
            
    except Exception as e:
        logger.exception("Exception in regenerate_topic")
        return JsonResponse({'success': False, 'error': 'Internal server error.'}, status=500)
    
def create_reinforcement_topic(course, student):
    """
    Create a reinforcement topic that summarizes all lessons in a course
    based on the student's performance
    """
    try:
        # Get all topics in the course
        course_topics = GeneratedTopic.objects.filter(chapter__course=course).order_by('order')
        
        # Get student's performance data
        weak_areas = []
        for topic in course_topics:
            try:
                completion = GeneratedTopicCompletion.objects.get(student=student, topic=topic)
                if completion.score < 70:  # Consider scores below 70% as weak areas
                    weak_areas.append({
                        'topic': topic,
                        'score': completion.score,
                        'wrong_answers': completion.wrong_answers if hasattr(completion, 'wrong_answers') else []
                    })
            except GeneratedTopicCompletion.DoesNotExist:
                pass
        
        # Create prompt for AI to generate reinforcement content
        prompt = f"""
        Create a reinforcement lesson for a C++ programming course titled "{course.title}".
        
        The student struggled with the following areas:
        {json.dumps([{'topic': area['topic'].title, 'score': area['score']} for area in weak_areas])}
        
        Please create a comprehensive summary that:
        1. Reviews all key concepts from the course
        2. Focuses especially on the areas where the student struggled
        3. Provides additional examples and explanations for difficult concepts
        4. Includes practice questions to reinforce learning
        5. Uses simple language and clear explanations
        
        Format the response as JSON with this structure:
        {{
            "title": "Course Reinforcement: {course.title}",
            "content": "Comprehensive review content...",
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
        
        # Generate content using AI
        model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})
        response = model.generate_content(prompt)
        
        # Parse the response
        try:
            topic_data = json.loads(response.text)
        except json.JSONDecodeError:
            # If it's not valid JSON, try to extract JSON from the response
            import re
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                topic_data = json.loads(json_match.group())
            else:
                logger.error("Could not extract JSON from AI response")
                return None
        
        # Create a new chapter for reinforcement topics
        reinforcement_chapter = GeneratedChapter.objects.filter(
            course=course,
            title="Reinforcement"
        ).first()
        
        if not reinforcement_chapter:
            reinforcement_chapter = GeneratedChapter.objects.create(
                course=course,
                title="Reinforcement",
                order=999  # Place at the end
            )
        
        # Create the reinforcement topic
        reinforcement_topic = GeneratedTopic.objects.create(
            chapter=reinforcement_chapter,
            title=topic_data.get('title', f"Reinforcement: {course.title}"),
            content=topic_data.get('content', ''),
            order=0,
            is_reinforcement=True
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
        
        logger.info(f"Created reinforcement topic for course: {course.title}")
        return reinforcement_topic
        
    except Exception as e:
        logger.error(f"Error creating reinforcement topic: {str(e)}")
        return None    

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
        
        Also generate a simpler quiz with 4 questions that focus on the core concepts.
        
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