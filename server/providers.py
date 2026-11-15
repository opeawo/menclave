"""Outbound adapters keep credentials server-side and restrict all destinations."""
import hashlib
import hmac
import json
import os
import socket
import ipaddress
from urllib.parse import urlsplit
import httpx
from server.services import DomainError,require,canonical

def validate_webhook(data):
    require(set(data)<={'url','secret_ref','enabled','events'},'Unsupported webhook settings.')
    parsed=urlsplit(data.get('url',''))
    allowed={v.strip() for v in os.environ.get('MENCLAVE_WEBHOOK_HOSTS','').split(',') if v.strip()}
    require(parsed.scheme=='https' and parsed.hostname in allowed and parsed.port in {None,443} and not parsed.username and not parsed.fragment,'Webhook host must be owner-allowlisted HTTPS on port 443.')
    require(data.get('secret_ref','').startswith('MENCLAVE_WEBHOOK_') and data['secret_ref'].replace('_','').isalnum(),'Use a webhook secret environment reference.')
    require(bool(os.environ.get(data['secret_ref'])),'Webhook signing secret is not configured.','unavailable')

def deliver_webhook(data,event):
    validate_webhook(data)
    host=urlsplit(data['url']).hostname
    addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    require(all(ipaddress.ip_address(info[4][0]).is_global for info in addresses),'Webhook DNS must resolve only to public addresses.')
    body=canonical(event).encode();secret=os.environ[data['secret_ref']].encode()
    signature=hmac.new(secret,body,hashlib.sha256).hexdigest()
    with httpx.Client(timeout=10,follow_redirects=False,trust_env=False) as client:
        response=client.post(data['url'],content=body,headers={'Content-Type':'application/json','X-Menclave-Signature':'sha256='+signature,'X-Menclave-Event':event['id']})
        require(200<=response.status_code<300,'Webhook delivery was not accepted.','provider_error')

def pxxl_enabled(tool):
    try: mapping=json.loads(os.environ.get('MENCLAVE_PXXL_TOOL_MAP','{}'))
    except ValueError:return False
    return bool(os.environ.get('MENCLAVE_PXXL_API_KEY') and os.environ.get('MENCLAVE_PXXL_PROJECT_ID') and isinstance(mapping.get(tool),dict))

def pxxl_operation(tool,args):
    require(pxxl_enabled(tool),'Pxxl adapter is not configured for this action.','unavailable')
    mapping=json.loads(os.environ['MENCLAVE_PXXL_TOOL_MAP'])[tool]
    project_field=mapping.get('project_field','project_id')
    require(project_field in {'project_id','projectId','project'},'Invalid trusted provider mapping.')
    params={project_field:os.environ['MENCLAVE_PXXL_PROJECT_ID']}
    if args.get('id'):
        field=mapping.get('deployment_field','deployment_id')
        require(field in {'deployment_id','deploymentId','version_id'},'Invalid deployment mapping.');params[field]=args['id']
    token=os.environ['MENCLAVE_PXXL_API_KEY']
    def rpc(client,method,values,id):
        response=client.post('https://mcp.pxxl.app/mcp',json={'jsonrpc':'2.0','id':id,'method':method,'params':values})
        if response.status_code>=400:raise DomainError('provider_error','Pxxl rejected the request; check connection permissions and provider access.')
        try:result=response.json()
        except ValueError:
            entries=[line[5:].strip() for line in response.text.splitlines() if line.startswith('data:')]
            require(bool(entries),'Unexpected Pxxl response.','provider_error');result=json.loads(entries[-1])
        require(not result.get('error'),'Pxxl operation failed.','provider_error')
        return result.get('result',{}),response.headers.get('Mcp-Session-Id')
    with httpx.Client(timeout=30,follow_redirects=False,trust_env=False,headers={'Authorization':'Bearer '+token,'Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-11-25'}) as client:
        _,session=rpc(client,'initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'Menclave server','version':'1.0'}},1)
        if session:client.headers['Mcp-Session-Id']=session
        client.post('https://mcp.pxxl.app/mcp',json={'jsonrpc':'2.0','method':'notifications/initialized'})
        result,_=rpc(client,'tools/call',{'name':mapping['name'],'arguments':params},2)
    require(not result.get('isError'),'Pxxl action failed. Inspect redacted provider diagnostics.','provider_error')
    value=result.get('structuredContent',{})
    if not value and result.get('content'):
        try:value=json.loads(result['content'][0].get('text','{}'))
        except ValueError:value={}
    # Provider outputs can include credentials and full environment values. Return a narrow projection.
    allowed={'id','project_id','deployment_id','version_id','status','state','url','created_at','name','deployments','items','commit_sha','branch'}
    def clean(data):
        if isinstance(data,dict):
            result={}
            for k,v in data.items():
                if k not in allowed:continue
                if k=='url':
                    parsed=urlsplit(str(v))
                    if parsed.scheme!='https' or parsed.username or parsed.query or parsed.fragment:continue
                result[k]=clean(v)
            return result
        if isinstance(data,list):return [clean(v) for v in data[:100]]
        if isinstance(data,str):return data[:500] if token not in data and not any(s in data.lower() for s in ['password=','bearer ','pxxl_']) else '[redacted]'
        return data
    return clean(value)
