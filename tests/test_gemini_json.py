"""Offline test of native Gemini request schema and parsing."""
import json
import pathlib
import sys
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from tactile import autolabel
from tactile import samples

class Response:
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self): return json.dumps({"candidates": [{"content": {"parts": [{"text": '[{"text":"Lens","x":0.3,"y":0.2,"tx":0.5,"ty":0.4}]'}]}}]}).encode()

captured = {}
def fake_urlopen(req, timeout):
    captured['url'] = req.full_url
    captured['body'] = json.loads(req.data)
    return Response()

autolabel.configure('gemini', 'AIza'+'x'*30, 'gemini-2.5-flash')
with patch('urllib.request.urlopen', fake_urlopen):
    out = autolabel.suggest_labels(samples.render('lens'))
assert out[0]['text'] == 'Lens'
assert 'models/gemini-2.5-flash:generateContent' in captured['url']
assert captured['body']['generationConfig']['responseMimeType'] == 'application/json'
assert captured['body']['generationConfig']['responseSchema']['type'] == 'ARRAY'
assert 'inline_data' in captured['body']['contents'][0]['parts'][1]
print('native Gemini JSON request and response test OK')
