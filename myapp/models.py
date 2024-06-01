from django.db import models

# 用戶資料
class user(models.Model):
    user_id = models.CharField(max_length=33, null=False, primary_key=True)
    exam_number = models.CharField(max_length=8, blank=True, default='')
    name = models.CharField(max_length=10, blank=True, default='')
    birthday = models.CharField(max_length=8, blank=True, default='')
    # password = models.CharField(max_length=50, blank=True, default='')
    question = models.TextField(blank=True, default='')
    def __str__(self) -> str:
        return self.user_id


# 考生資料 (學校事先輸入)
class examinee(models.Model):
    exam_number = models.CharField(max_length=8, null=False, primary_key=True)
    name = models.CharField(max_length=10, blank=True, default='')
    birthday = models.CharField(max_length=8, blank=True, default='')
    def __str__(self) -> str:
        return self.exam_number