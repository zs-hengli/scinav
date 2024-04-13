import os

from celery import Celery
from celery.schedules import crontab
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

# 设置环境变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# 实例化
app = Celery('core')

# namespace='CELERY'作用是允许你在Django配置文件中对Celery进行配置
# 但所有Celery配置项必须以CELERY开头，防止冲突
app.config_from_object('django.conf:settings', namespace='CELERY')

app.conf.beat_schedule = {
    'async-document-library-every-minute': {
        'task': 'document.tasks.async_document_library_task',
        'schedule': crontab(minute='*'),
    },
}
app.conf.broker_connection_retry_on_startup = True
# 自动从Django的已注册app中发现任务
app.autodiscover_tasks()


# 一个测试任务
@app.task(bind=True)
def debug_task(self):
    logger.info(f'debug_task Request: {self.request!r}')

