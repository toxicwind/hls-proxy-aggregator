#!/usr/bin/env python3
"""
m3u_loader.py — Streaming M3U parser. No giant arrays. Writes JSONL directly.
"""
import re, hashlib, os
from urllib.parse import urlparse

EN_POS = {
    'uk','us','usa','british','american','cnn','bbc','fox','nbc','abc','cbs',
    'hbo','showtime','amc','fx','sky','espn','discovery','nat geo','history',
    'animal planet','cartoon network','disney','nick','pbs','boomerang',
    'comedy central','tnt','tbs','syfy','sci-fi','mtv','vh1','bet','e!',
    'bravo','ae','tlc','food network','travel channel','weather channel',
    'bloomberg','cnbc','msnbc',
}
EN_NEG = {
    'espanol','spanish','latino','latam','mexico','francais','french','france',
    'deutsch','german','rtl','russkiy','russian','russia','chinese','china',
    'cctv','arabic','aljazeera','mbc','hindi','india','bollywood','portugues',
    'italiano','turkce','polski','greek','dutch','swedish','norwegian',
}

def detect_lang(title, group):
    t = (title + " " + group).lower()
    if any(w in t for w in EN_NEG):
        return None
    if any(w in t for w in EN_POS):
        return "en"
    ascii_ratio = sum(1 for c in t if ord(c) < 128) / max(len(t), 1)
    if ascii_ratio < 0.85:
        return None
    return "en"

def detect_cat(title, group, ct):
    t = (title + " " + group).lower()
    if ct == "audio" or "radio" in t:
        return "Radio"
    if any(w in t for w in ['movie','film','cinema','hbo','showtime','starz']):
        return "Movies"
    if any(w in t for w in ['news','cnn','bbc','fox news','msnbc','sky news','bloomberg','cnbc']):
        return "News"
    if any(w in t for w in ['sport','espn','nfl','nba','ufc','wwe','mlb','nhl','f1','golf','tennis']):
        return "Sports"
    if any(w in t for w in ['music','mtv','vh1','bet','trace']):
        return "Music"
    if any(w in t for w in ['kid','cartoon','disney','nick','pbs','cbeebies']):
        return "Kids"
    if any(w in t for w in ['doc','discovery','nat geo','history','animal planet']):
        return "Documentary"
    if any(w in t for w in ['adult','xxx','playboy','hustler']):
        return "Adult"
    if any(w in t for w in ['comedy','laugh','stand-up']):
        return "Comedy"
    if any(w in t for w in ['horror','terror','scream']):
        return "Horror"
    return "General"

def score_q(title, domain):
    t = title.lower()
    s = 25
    if any(w in t for w in ['1080p','fhd','full hd']): s = 100
    elif any(w in t for w in ['720p','hd']): s = 70
    elif any(w in t for w in ['480p','sd']): s = 40
    elif any(w in t for w in ['360p','240p']): s = 10
    pref = ['jmp2.uk','1tv41.icu','p2premium.club','flixtv.uk','dplatino.net','mundo2.pro','mundo2.vip','ceoapps.org']
    for idx, d in enumerate(pref):
        if d in domain:
            s += max(0, 15 - idx * 2)
            break
    return s

def parse_m3u_file(filepath, out_fh, seen):
    """Parse single M3U file, write JSONL records directly."""
    current = {'source_m3u': os.path.basename(filepath)}
    kept = 0
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#EXTINF'):
                for attr in ['tvg-id','tvg-name','tvg-logo','group-title']:
                    m = re.search(rf'{attr}="([^"]*)"', line)
                    if m:
                        current[attr.replace('-','_')] = m.group(1)
                m = re.search(r',(.+)$', line)
                if m:
                    current['title'] = m.group(1).strip()
            elif line.startswith('http'):
                url = line.strip().strip('"').strip("'")
                if url in seen:
                    current = {'source_m3u': os.path.basename(filepath)}
                    continue
                seen.add(url)

                parsed = urlparse(url)
                path = parsed.path.lower()
                domain = parsed.netloc.split(':')[0]

                if any(x in path for x in ['.jpg','.png','.jpeg','.webp','.gif']):
                    current = {'source_m3u': os.path.basename(filepath)}
                    continue

                if '.m3u8' in path: ct = 'hls'
                elif '.ts' in path: ct = 'mpegts'
                elif '.mp4' in path: ct = 'mp4'
                elif any(x in path for x in ['.mp3','.aac','.ogg']): ct = 'audio'
                else: ct = 'unknown'

                lang = detect_lang(current.get('title',''), current.get('group_title',''))
                if not lang:
                    current = {'source_m3u': os.path.basename(filepath)}
                    continue

                cat = detect_cat(current.get('title',''), current.get('group_title',''), ct)
                score = score_q(current.get('title',''), domain)

                rec = {
                    'id': hashlib.sha256(url.encode()).hexdigest()[:16],
                    'title': current.get('title',''),
                    'url': url,
                    'group': current.get('group_title',''),
                    'category': cat,
                    'language': lang,
                    'quality_score': score,
                    'content_type': ct,
                    'is_radio': ct == 'audio',
                    'has_auth': any(k in parsed.query.lower() for k in ['token=','auth=','signature=','mac=','sn=']),
                    'domain': domain,
                    'scheme': parsed.scheme,
                    'verification_status': 'pending',
                    'discovery_method': 'original',
                    'fallback_chain': [url],
                }
                out_fh.write(json.dumps(rec, ensure_ascii=False, separators=(',',':')) + '\n')
                kept += 1
                current = {'source_m3u': os.path.basename(filepath)}
    return kept

def main():
    import json
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(base, 'source', 'Dji-you-main')
    db_dir = os.path.join(base, 'db')
    os.makedirs(db_dir, exist_ok=True)
    jsonl_path = os.path.join(db_dir, 'channels.jsonl')

    m3u_files = [f for f in os.listdir(src) if f.endswith('.m3u')]
    print(f"[LOADER] {len(m3u_files)} M3U files")

    seen = set()
    total_kept = 0
    total_urls = 0

    with open(jsonl_path, 'w', encoding='utf-8') as out:
        for mf in sorted(m3u_files):
            fp = os.path.join(src, mf)
            kept = parse_m3u_file(fp, out, seen)
            total_kept += kept
            print(f"  {mf}: {kept} kept")

    print(f"[LOADER] Total kept: {total_kept}, Unique URLs: {len(seen)}")
    print(f"[LOADER] Written to {jsonl_path}")

if __name__ == '__main__':
    main()
