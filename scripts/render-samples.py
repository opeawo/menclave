import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.editorial import render_blocks
print(json.dumps({story['slug']:render_blocks(story) for story in json.loads(Path('content/stories.json').read_text())}))
