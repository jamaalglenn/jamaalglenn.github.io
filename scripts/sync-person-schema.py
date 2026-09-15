#!/usr/bin/env python3
"""Sync the canonical Person JSON-LD into every public HTML page.
Edit schema/person.json, then run: python3 scripts/sync-person-schema.py
Preview, parked, and private dashboard pages are intentionally excluded.
"""
from pathlib import Path
import json,re
root=Path(__file__).resolve().parents[1]
data=json.loads((root/'schema/person.json').read_text())
payload=json.dumps(data,indent=2,ensure_ascii=False)
block=f'<script id="jamaal-person-schema" type="application/ld+json">\n{payload}\n</script>'
pages=[root/n for n in ['index.html','about.html','advisory.html','speaking.html','newsletter.html','news.html','contact.html']]
pages+=sorted((root/'release').glob('*.html'))
pattern=re.compile(r'<script[^>]*(?:id=["\']jamaal-person-schema["\']|type=["\']application/ld\+json["\'])[^>]*>.*?</script>\s*',re.I|re.S)
for page in pages:
    text=page.read_text()
    # The only pre-existing JSON-LD was the older Person block on index.html.
    text,n=pattern.subn('',text)
    if '</head>' not in text: raise RuntimeError(f'No </head> in {page}')
    text=text.replace('</head>',block+'\n</head>',1)
    page.write_text(text)
print(f'Synced Person schema to {len(pages)} public pages.')
