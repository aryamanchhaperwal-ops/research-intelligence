import urllib.request
import json
import base64

def req(url, data=None, method='GET'):
    if data:
        data = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print('Error:', e)
        if hasattr(e, 'read'):
            print(e.read().decode())
        return None

def run():
    base = 'http://localhost:8001/api'
    
    p = req(f'{base}/projects', {
        'name': 'E2E Test Final 3',
        'domain': 'technology',
        'researchQuestion': 'How do companies use AI?'
    }, 'POST')
    slug = p['data']['slug']
    print('Project:', slug)

    s = req(f'{base}/projects/{slug}/sources', {
        'title': 'Test Article',
        'kind': 'article',
        'ingest': True,
        'content': 'According to OpenAI, GPT-4 is a massive leap that shows that AI is advancing. In 2023, Microsoft invested heavily in OpenAI, which confirmed their commitment. Google reported that they responded with Gemini, achieving 90% accuracy. Stanford University found that DeepMind also made progress in artificial intelligence.',
        'url': ''
    }, 'POST')
    print('Source:', s['data']['status'])

    f = req(f'{base}/projects/{slug}/findings/generate', {}, 'POST')
    print('Findings generated:', f['data']['count'])

    r = req(f'{base}/projects/{slug}/report')
    metrics = r['data']['metrics']
    print('Report Metrics:', metrics)

run()
