import os
from server.web import create_app
os.environ.setdefault('ENCLAVE_ENV','production')
app = create_app()
