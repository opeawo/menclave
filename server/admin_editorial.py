"""Small owner studio using the same service contract as assistants."""
import json
import secrets
from flask import request,jsonify,redirect
from server.services import SCOPES,DomainError
from server.tools import dispatch

def install_editorial(app,platform,session,trusted,page):
    owner={'id':'owner-ui','scopes':sorted(SCOPES)}
    @app.get('/admin/preview/<id>')
    def preview(id):
        if not session():return redirect('/admin')
        try:result=dispatch(platform,'content_preview',{'id':id},owner)
        except DomainError:return jsonify(error='Content unavailable.'),404
        # preview_html is rendered by a fixed escaping template in the shared service.
        return page('Editorial preview','{{preview|safe}}',preview=result['preview_html'])
    @app.get('/admin/editorial')
    def studio():
        current=session()
        if not current:return redirect('/admin')
        with platform.store.connect() as db:items=platform.list(db,limit=100)['items']
        return page('Editorial studio','''<p><a href="/admin">Owner control room</a> · <a href="/magazine">Public magazine</a></p><h2>Create a draft</h2><p>Paste a content object with title, slug, deck, category and sections (plain heading/body text). Content remains a draft until publishing is approved.</p><form method="post" action="/admin/editorial/create"><input type="hidden" name="csrf" value="{{csrf}}"><label>Content JSON<textarea name="data" rows="10" required>{"title":"New story","slug":"new-story","deck":"A thoughtful introduction.","category":"Faith & Purpose","concept":true,"sections":[{"heading":"Begin here","body":"Your editorial copy."}]}</textarea></label><button class="button">Create draft</button></form><h2>Content</h2>{% for item in items if item.kind in ['article','interview','news','page','newsletter'] %}<article class="moderation-item"><h3>{{item.data.title}}</h3><p>{{item.status}} · revision {{item.revision}}</p><a href="/magazine/{{item.data.slug}}">Public URL</a> · <a href="/admin/preview/{{item.id}}">Private preview</a><form method="post" action="/admin/editorial/update"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="id" value="{{item.id}}"><input type="hidden" name="revision" value="{{item.revision}}"><textarea name="data" rows="8">{{item.data|tojson}}</textarea><button>Save draft changes</button></form><form method="post" action="/admin/editorial/publish"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="id" value="{{item.id}}"><input type="hidden" name="revision" value="{{item.revision}}"><button>Request publication</button></form></article>{% endfor %}''',items=items,csrf=current['csrf'])
    @app.post('/admin/editorial/<action>')
    def edit(action):
        if not trusted():return jsonify(error='Owner session required.'),403
        args={'idempotency_key':secrets.token_urlsafe(20)}
        try:
            if action=='create':name='content_create_draft';args['data']=json.loads(request.form['data'])
            elif action in {'update','publish'}:
                name='content_update' if action=='update' else 'content_publish';args.update(id=request.form['id'],expected_revision=int(request.form['revision']))
                if action=='update':args['data']=json.loads(request.form['data'])
            else:return jsonify(error='Unknown action.'),404
            result=dispatch(platform,name,args,owner)
            if result.get('approval_required'):return redirect('/admin#approvals')
            return redirect('/admin/editorial')
        except (ValueError,KeyError,DomainError) as error:return page('Check the change','<p>{{message}}</p><a href="/admin/editorial">Return</a>',message=str(error)),400
    @app.post('/admin/commit')
    def commit():
        if not trusted():return jsonify(error='Owner session required.'),403
        try:
            dispatch(platform,'changes_commit',{'plan_id':request.form['plan_id'],'idempotency_key':secrets.token_urlsafe(20)},owner)
        except DomainError as error:return jsonify(error=str(error)),409
        return redirect('/admin/editorial')
