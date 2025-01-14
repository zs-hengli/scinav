import os

from celery import Celery, shared_task
from celery.schedules import crontab, timedelta
from celery.utils.log import get_task_logger
from celery.signals import setup_logging

logger = get_task_logger(__name__)

# 设置环境变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# 实例化
app = Celery('core')

# namespace='CELERY'作用是允许你在Django配置文件中对Celery进行配置
# 但所有Celery配置项必须以CELERY开头，防止冲突
app.config_from_object('django.conf:settings', namespace='CELERY')


@setup_logging.connect
def config_loggers(*args, **kwags):
    from logging.config import dictConfig
    from django.conf import settings
    dictConfig(settings.LOGGING)


app.conf.timezone = 'Asia/Shanghai'

app.conf.beat_schedule = {
    'async-document-library-every-10seconds': {
        'task': 'document.tasks.async_document_library_task',
        'schedule': timedelta(seconds=10),
    },
    'async-publish-bot-every-minute': {
        'task': 'document.tasks.async_schedule_publish_bot_task',
        'schedule': crontab(minute='*'),
    },
    # 'async-daily-member-status-every-day': {
    #     'task': 'document.tasks.async_daily_member_status',
    #     'schedule': crontab(minute=1, hour=0),
    # },
    'async_daily_duration_award-every-day': {
        'task': 'document.tasks.async_daily_duration_award',
        'schedule': crontab(minute=6, hour=0),
    },
}
app.conf.broker_connection_retry_on_startup = True
# 自动从Django的已注册app中发现任务
app.autodiscover_tasks()


# 一个测试任务
@shared_task(bind=True)
def debug_task(self, a, b):
    logger.info(f'debug_task a: {a}, b: {b}')
    """
    def debug_task.apply_async(args=(2, 3), countdown=5)
    """
    logger.info(f'debug_task Request: {self.request!r}')

