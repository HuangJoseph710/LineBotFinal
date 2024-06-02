from django.contrib import admin
from myapp.models import *

# Register your models here.
class userAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'exam_number','name', 'birthday')
admin.site.register(user, userAdmin)

class examineeAdmin(admin.ModelAdmin):
    list_display = ('exam_number', 'name', 'birthday')
admin.site.register(examinee, examineeAdmin)