from django.contrib import admin
from .models import Course, Module, Lesson

class LessonInline(admin.StackedInline):
    model = Lesson
    extra = 1
    fields = ('title', 'order', 'content', 'content_type', 'difficulty', 'estimated_time')

class ModuleInline(admin.StackedInline):
    model = Module
    extra = 1
    fields = ('title', 'order', 'description')
    inlines = [LessonInline]

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    inlines = [ModuleInline]
    list_display = ('title', 'created_at')
    search_fields = ('title', 'description')

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order')
    list_filter = ('course',)
    search_fields = ('title', 'description')
    inlines = [LessonInline]

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'module', 'order', 'content_type', 'difficulty')
    list_filter = ('module__course', 'content_type', 'difficulty')
    search_fields = ('title', 'content')
    ordering = ('module__course', 'module__order', 'order')