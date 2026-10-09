#!/usr/bin/env python3
"""Update only the two existing newsletter lists from the owner's public RSS."""
import subprocess
import argparse, datetime, email.utils, html, json, pathlib, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
FEED='https://jamaalglenn.substack.com/feed'
def fetch(url):
 return subprocess.run(['curl','--fail','--location','--silent','--show-error','--max-time','45','--user-agent','Mozilla/5.0','--header','Accept: application/rss+xml, application/xml, text/xml, */*',url],check=True,capture_output=True).stdout
def date_label(pub):
 d=email.utils.parsedate_to_datetime(pub)
 return f'{d:%B} {d.day}, {d.year}'
def post_url(url):
 p=urllib.parse.urlsplit(url)
 if p.scheme!='https' or p.hostname!='jamaalglenn.substack.com' or not p.path.startswith('/p/'):raise ValueError('Unexpected post URL')
 return url

def items(feed):
 root=ET.fromstring(feed); result=[];seen=set()
 for i in root.findall('./channel/item'):
  url=post_url(i.findtext('link','').strip())
  if url in seen:continue
  seen.add(url)
  title=i.findtext('title','').strip();pub=i.findtext('pubDate','').strip()
  if not title or not pub:raise ValueError('Missing title/date')
  desc=html.unescape(re.sub('<[^>]+>',' ',i.findtext('description','')));desc=' '.join(desc.split())
  enclosure=i.find('enclosure'); image=enclosure.get('url','') if enclosure is not None else ''
  if image and (urllib.parse.urlsplit(image).scheme!='https' or urllib.parse.urlsplit(image).hostname not in ['substackcdn.com','substack-post-media.s3.amazonaws.com']):raise ValueError('Unexpected image source')
  result.append({'title':title,'url':url,'date':date_label(pub),'description':desc,'image':image,'timestamp':email.utils.parsedate_to_datetime(pub).timestamp()})
 if not result:raise ValueError('Empty feed; refusing to wipe site')
 return sorted(result,key=lambda x:x['timestamp'],reverse=True)
def href(block):
 m=re.search(r'href=["\'](https://jamaalglenn\.substack\.com/p/[^"\']+)',block)
 if not m:raise ValueError('Unexpected existing post markup')
 return html.unescape(m.group(1))
def merge(existing,posts,count,render):
 urls={href(b) for b in existing}; anchor=href(existing[0]) if existing else None
 anchor_ts=next((p['timestamp'] for p in posts if p['url']==anchor),None)
 # Add only posts newer than current lead, never revive older curated omissions.
 if anchor_ts is None:raise ValueError('Current lead is absent from RSS; manual review needed')
 fresh=[p for p in posts if p['url'] not in urls and p['timestamp']>anchor_ts]
 return ([render(p) for p in fresh]+existing)[:count],fresh

def e(x):return html.escape(x,quote=True)
def link(p):return f'<li><span class="what"><a href="{e(p["url"])}">{e(p["title"])}</a></span><time class="letter-post-date">{e(p["date"])}</time></li>'
def card(p):
 image=f'<a class="edition-image" href="{e(p["url"])}"><img alt="" loading="lazy" src="{e(p["image"])}"/></a>' if p['image'] else ''
 return f'<article class="edition-card">{image}<h3><a href="{e(p["url"])}">{e(p["title"])}</a></h3><p class="edition-sub">{e(p["description"])}</p><time class="edition-date">{e(p["date"])}</time></article>'
def update(root,posts,dry):
 changes={}; expected={};added=[]
 for name,pat,tag,limit,renderer in [('index.html',r'(<ul\b[^>]*\bid="letter-post-list"[^>]*>)(.*?)(</ul>)','li',5,link),('newsletter.html',r'(<div\b[^>]*class="edition-grid"[^>]*>)(.*?)(</div>)','article',6,card)]:
  path=root/name;text=path.read_text();comments=[(c.start(),c.end()) for c in re.finditer(r'<!--.*?-->',text,re.S)]
  matches=[m for m in re.finditer(pat,text,re.S) if not any(a<=m.start()<b for a,b in comments)]
  if len(matches)!=1:raise ValueError(f'{name}: expected one list, found {len(matches)}')
  m=matches[0];existing=re.findall(r'<'+tag+r'\b.*?</'+tag+'>',m.group(2),re.S)
  if len(existing)!=limit:raise ValueError(f'{name}: expected {limit} existing entries')
  merged,fresh=merge(existing,posts,limit,renderer);expected[name]=[href(b) for b in merged];added +=fresh
  if merged!=existing:changes[path]=text[:m.start(2)]+'\n'+'\n'.join(merged)+'\n'+text[m.end(2):]
 for path,text in changes.items():
  if not dry:path.write_text(text)
 manifest={'feed':FEED,'expected':expected,'added':list({p['url']:p for p in added}.values()),'changed':bool(changes)}
 print(json.dumps(manifest,indent=2))
 return manifest

def verify(base,manifest):
 for name,urls in manifest['expected'].items():
  u=base.rstrip('/')+('/' if name=='index.html' else '/'+name)+'?rss_verify='+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')
  text=fetch(u).decode();pat=r'<ul\b[^>]*\bid="letter-post-list"[^>]*>(.*?)</ul>' if name=='index.html' else r'<div\b[^>]*class="edition-grid"[^>]*>(.*?)</div>'
  text=re.sub(r'<!--.*?-->','',text,flags=re.S)
  m=re.search(pat,text,re.S)
  if not m:raise ValueError(f'{name}: live list not found')
  tag='li' if name=='index.html' else 'article';actual=[href(b) for b in re.findall(r'<'+tag+r'\b.*?</'+tag+'>',m.group(1),re.S)]
  if actual!=urls:raise ValueError(f'{name}: deployed list differs from expected')
  print(f'Verified {u}: {len(urls)} posts in expected order')

def main():
 a=argparse.ArgumentParser();a.add_argument('--root',default='.');a.add_argument('--feed-file');a.add_argument('--dry-run',action='store_true');a.add_argument('--manifest',default='/tmp/letter-posts-manifest.json');a.add_argument('--verify-base');args=a.parse_args()
 if args.verify_base:verify(args.verify_base,json.loads(pathlib.Path(args.manifest).read_text()));return
 feed=pathlib.Path(args.feed_file).read_bytes() if args.feed_file else fetch(FEED)
 manifest=update(pathlib.Path(args.root),items(feed),args.dry_run);pathlib.Path(args.manifest).write_text(json.dumps(manifest))
if __name__=='__main__':main()
