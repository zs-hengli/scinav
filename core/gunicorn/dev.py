import multiprocessing
import os


bind = ['0.0.0.0:8000']
daemon = False
# workers = multiprocessing.cpu_count() * 2 + 1
workers = multiprocessing.cpu_count()
# threads = 2
preload_app = True
# max_requests = 100
worker_class = 'gevent'
timeout = 1800
# enable_stdio_inheritance = True

loglevel = 'debug'
reload = True
if not os.path.exists('logs'):
    os.makedirs('logs')
accesslog = "logs/gunicorn_access.log"      # 访问日志文件
errorlog = "logs/gunicorn_error.log"        # 错误日志文件