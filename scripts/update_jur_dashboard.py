#!/usr/bin/env python3
"""Update the JUR dashboard from validated official Jobindsats API series."""
from __future__ import annotations
import json, math, re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from discover_jur_sources import api_get

BASE=Path(__file__).resolve().parents[1]
DATA_PATH=BASE/'data/dashboard-data.json'; HTML_PATH=BASE/'index.html'
DATA_START='const DATA='; DATA_END=';\nconst C='
AKASSE_NAMES={
'A-kassen A&Til':'A-kassen A&Til','A-kassen Ase':'ASE','A-kassen Frie':'A-kassen Frie',
'A-kassen for Journalistik, Komm. og Sprog':'A-kassen for Journalistik, Kommunikation & Sprog',
'Akademikernes A-kasse':'Akademikernes A-kasse','BUPL A-kasse':'Børne- og Ungdomspædagogernes Landsdækkende A-kasse',
'CA A-kasse':'CA A-kasse & Karriereudvikling','Det Faglige Hus A-kasse':'Det Faglige Hus - A-kasse',
'Din Faglige A-Kasse':'Din Faglige A-kasse','Din Sundhedsfaglige A-kasse':'Din Sundhedsfaglige A-kasse',
'FOAs A-kasse':'FOAs A-kasse','Faglig Fælles (3F) A-kasse':'Faglig Fælles A-kasse','HK /Danmarks A-kasse':'HK A-kasse',
'Kristelig A-Kasse':'Kristelig A-kasse','Lederne A-kasse':'Lederne A-kasse','Lærernes A-kasse':'Lærernes a-kasse',
'Magistrenes A-kasse':'Magistrenes A-kasse','Metalarbejdernes A-Kasse':'Metal A-kasse','Min A-kasse':'Min A-kasse',
'Socialpædagogernes A-Kasse':'Socialpædagogernes A-kasse','Teknikernes A-Kasse':'Teknikernes A-kasse'}

def records(path):
 r=api_get(path); cols=r.get('columns'); rows=r.get('rows')
 if not isinstance(cols,list) or not isinstance(rows,list): raise RuntimeError('Jobindsats svarede ikke med columns og rows')
 return [dict(zip(cols,row)) for row in rows]

def num(v):
 if v is None or isinstance(v,bool): return None
 if isinstance(v,(int,float)): x=float(v)
 else:
  t=str(v).strip().replace('\xa0','').replace(' ','')
  if not t or t in {'-','..'}: return None
  x=float(t.replace('.','').replace(',','.') if ',' in t else t)
 if not math.isfinite(x): return None
 return int(x) if x.is_integer() else round(x,4)

def year_ago(p):
 m=re.fullmatch(r'(\d{4})(M\d{2}|Q\d{2})',p); return f'{int(m.group(1))-1}{m.group(2)}' if m else ''

def kpi(sec,values):
 valid=[(str(p),num(v)) for p,v in zip(sec['labels'],values) if num(v) is not None]
 if not valid:return
 p,v=valid[-1]; y=year_ago(p); lookup=dict(valid)
 sec['kpi']={'period':p,'value':v,'lastYearPeriod':y,'lastYearValue':lookup.get(y),'unit':sec.get('kpi',{}).get('unit','count')}

def merge_arrays(sec,updates):
 old_labels=list(sec['labels']); labels=sorted(set(old_labels)|{p for p in updates if not old_labels or p>=old_labels[0]})
 keys={x for v in updates.values() for x in v}|{x for x,v in sec.items() if isinstance(v,list) and x!='labels'}
 old={p:{x:sec[x][i] if i<len(sec[x]) else None for x in keys if x in sec} for i,p in enumerate(old_labels)}
 for p,v in updates.items():
  if p in labels: old.setdefault(p,{}).update(v)
 sec['labels']=labels
 for x in keys: sec[x]=[old.get(p,{}).get(x) for p in labels]

def merge_named(sec,updates):
 old_labels=list(sec['labels']); labels=sorted(set(old_labels)|{p for p in updates if not old_labels or p>=old_labels[0]})
 combined={n:dict(zip(old_labels,v)) for n,v in sec['series'].items()}
 for p,vals in updates.items():
  if p in labels:
   for n,v in vals.items(): combined.setdefault(n,{})[p]=v
 sec['labels']=labels; sec['series']={n:[combined[n].get(p) for p in labels] for n in sec['series']}

def merge_akasse(sec,rows,column):
 old_labels=list(sec['labels']); grouped=defaultdict(dict)
 for row in rows:
  name=AKASSE_NAMES.get(row.get('A-kasse'))
  if name: grouped[str(row['Periode'])][name]=num(row.get(column))
 labels=sorted(set(old_labels)|{p for p in grouped if not old_labels or p>=old_labels[0]})
 combined={n:dict(zip(old_labels,v)) for n,v in sec['byAkasse'].items()}
 for p,vals in grouped.items():
  for n,v in vals.items(): combined.setdefault(n,{})[p]=v
 sec['labels']=labels
 sec['byAkasse']={n:[combined.get(n,{}).get(p) for p in labels] for n in sec['byAkasse']}
 old_total=dict(zip(old_labels,sec['total'])); totals=[]
 for p in labels:
  vals=[combined.get(n,{}).get(p) for n in sec['byAkasse']]
  totals.append(round(sum(v for v in vals if v is not None)) if any(v is not None for v in vals) else old_total.get(p))
 sec['total']=totals; kpi(sec,totals)

def refresh_unemployment(d):
 rows=records('data/y25i01?mgroup.*=*&period.M=latest:120&hierarchy._nykom=/&hierarchy._ygrpi09=/&hierarchy._akassebl=*&format=json')
 merge_akasse(d['sections']['unemploymentAkasser'],rows,'Antal ledige fuldtidspersoner')

def refresh_longterm(d):
 rows=records('data/y25i09?mgroup.*=*&period.M=latest:120&hierarchy._nykom=/&hierarchy._ygrpi09=/&hierarchy._akassebl=*&format=json')
 merge_akasse(d['sections']['longTermUnemployment'],rows,'Antal langtidsledige fuldtidspersoner')

def refresh_activation(d):
 rows=records('data/y01c01?mgroup.*=*&period.M=latest:120&hierarchy._nykom=/&hierarchy._akassedp=/&hierarchy._tilb_2ptv=*&format=json')
 names={'Tilbud i alt':'Tilbud i alt','Ordinær uddannelse i alt':'Ordinær uddannelse','Øvrige vejlednings- og opkvalificeringsforløb':'Øvrig vejl./opkval. (ØVO)','Ansættelse med løntilskud i alt':'Løntilskud','Virksomhedspraktik i alt':'Virksomhedspraktik','Nytteindsats i alt':'Nytteindsats'}
 updates=defaultdict(dict)
 for r in rows:
  n=names.get(r.get('Tilbud'))
  if n: updates[str(r['Periode'])][n]=num(r.get('Antal fuldtidsaktiverede'))
 sec=d['sections']['activationOffers']; merge_named(sec,updates); kpi(sec,sec['series']['Tilbud i alt'])

def refresh_notices(d):
 rows=records('data/y25i05?mgroup.*=*&period.M=latest:120&hierarchy._nykom=/&format=json')
 sec=d['sections']['notices']; merge_arrays(sec,{str(r['Periode']):{'total':num(r.get('Varslinger, antal personer'))} for r in rows}); kpi(sec,sec['total'])

def refresh_worksharing(d):
 rows=records('data/y25i06?mgroup.*=*&period.M=latest:120&hierarchy._nykom=/&hierarchy._var13uger=*&format=json'); updates=defaultdict(dict)
 for r in rows:
  key='under13Weeks' if 'op til 13' in str(r.get('Arbejdsfordelingstype','')) else 'over13Weeks'; updates[str(r['Periode'])][key]=num(r.get('Antal personer'))
 for v in updates.values():
  if v.get('under13Weeks') is not None and v.get('over13Weeks') is not None:v['total']=v['under13Weeks']+v['over13Weeks']
 sec=d['sections']['workSharing']; merge_arrays(sec,updates); kpi(sec,sec['total'])

def refresh_graduates(d):
 rows=records('data/y01dia02?mgroup.*=*&period.M=latest:120&hierarchy._nykom=/&hierarchy._akassedp=*&format=json')
 merge_akasse(d['sections']['graduateUnemployed'],rows,'Antal dimittendledige fuldtidspersoner')

def refresh_expired(d):
 rows=records('data/y01ud01di?mgroup.*=*&period.M=latest:120&hierarchy._hele_landet=/&hierarchy._akassedp=/&hierarchy._dimittend=*&hierarchy._forlang=/&format=json'); updates=defaultdict(dict)
 for r in rows: updates[str(r['Periode'])][str(r['Dimittend'])]=num(r.get('Antal personer med opbrugt dagpengeret'))
 sec=d['sections']['graduateExpiredBenefits']; merge_named(sec,updates); kpi(sec,sec['series']['Ledige i alt'])

def refresh_sanctions(d):
 rows=records('data/y01h01?mgroup.*=*&period.Q=latest:40&hierarchy._nykom=/&hierarchy._akassedp=*&format=json')
 cols={'total':'Antal sanktioner i alt','excludedPeriod':'Antal sanktioner fordelt på type: Udelukkes fra dagpenge i en periode','quarantine':'Antal sanktioner fordelt på type: Karantæne (selvforskyldt ledighed)','repetition':'Antal sanktioner fordelt på type: Gentagelsesvirkning (arbejdskrav)','other':'Antal sanktioner fordelt på type: Andre (arbejdskrav)','share':'Andel sanktionerede ledige'}
 sec=d['sections']['sanctions']; old=list(sec['labels']); labels=sorted(set(old)|{str(r['Periode']) for r in rows if str(r['Periode'])>=old[0]}); series={x:dict(zip(old,sec['series'][x])) for x in cols}; by={n:{x:dict(zip(old,v[x])) for x in cols} for n,v in sec['byAkasse'].items()}
 for r in rows:
  p=str(r['Periode']); name=r.get('A-kasse')
  target=series if name=='A-kasse i alt' else by.get(AKASSE_NAMES.get(name))
  if target:
   for x,c in cols.items(): target[x][p]=num(r.get(c))
 sec['labels']=labels; sec['series']={x:[v.get(p) for p in labels] for x,v in series.items()}; sec['byAkasse']={n:{x:[v[x].get(p) for p in labels] for x in cols} for n,v in by.items()}; kpi(sec,sec['series']['total'])

def load_data():
 if DATA_PATH.exists():return json.loads(DATA_PATH.read_text(encoding='utf-8')),True
 html=HTML_PATH.read_text(encoding='utf-8'); a=html.find(DATA_START); b=html.find(DATA_END,a)
 if a<0 or b<0:raise RuntimeError('Kunne ikke udlæse DATA-blokken fra index.html')
 return json.loads(html[a+len(DATA_START):b]),False

def render(data):
 html=HTML_PATH.read_text(encoding='utf-8'); a=html.find(DATA_START); b=html.find(DATA_END,a)
 if a<0 or b<0:raise RuntimeError('Kunne ikke finde DATA-blokken i index.html')
 payload=json.dumps(data,ensure_ascii=False,separators=(',',':')); HTML_PATH.write_text(html[:a+len(DATA_START)]+payload+html[b:],encoding='utf-8')

def main():
 data,had=load_data(); before=json.dumps(data,ensure_ascii=False,sort_keys=True)
 for fn in (refresh_unemployment,refresh_longterm,refresh_activation,refresh_notices,refresh_worksharing,refresh_graduates,refresh_expired,refresh_sanctions):fn(data)
 if before==json.dumps(data,ensure_ascii=False,sort_keys=True) and had: print('Ingen nye eller ændrede Jobindsats-tal.'); return
 now=datetime.now(ZoneInfo('Europe/Copenhagen')); months=['januar','februar','marts','april','maj','juni','juli','august','september','oktober','november','december']
 data['meta']['versionDate']=f'{now.day}. {months[now.month-1]} {now.year}'; data['meta']['sourceFile']='Officielle API-kilder med tidligere Excel-data som fallback'
 DATA_PATH.parent.mkdir(parents=True,exist_ok=True); DATA_PATH.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); render(data); print(f"JUR-dashboardet er opdateret: {data['meta']['versionDate']}.")
if __name__=='__main__':main()
