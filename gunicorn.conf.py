import os
bind = '0.0.0.0:' + os.environ.get('PORT','8000')
workers = 1
threads = 4
worker_class = 'gthread'
timeout = 30
accesslog = None
errorlog = '-'
umask = 0o077
