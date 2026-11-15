import os
from server.web import create_app
from server.mcp_app import create_asgi
os.environ.setdefault('ENCLAVE_ENV','production')
web=create_app()
app=create_asgi(web,web.extensions['platform'])
