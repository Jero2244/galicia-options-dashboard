from pathlib import Path
from datetime import date
import openpyxl,json,re,math,sys,statistics,collections,csv
import numpy as np
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sys.path.insert(0,r'C:/Users/HP Laptop/.agents/skills/option-pricing/scripts')
from option_pricing import bs_price,binomial_price,bs_greeks
source=Path(r'C:/Users/HP Laptop/Downloads/options_data.xlsx')
w=openpyxl.load_workbook(source,read_only=True,data_only=True)
wf=openpyxl.load_workbook(source,read_only=True,data_only=False)
raw=list(w['Sheet1'].values); formulas=list(wf['Sheet1'].values)
stock=json.loads((OUT/'ppi_stock_raw.json').read_text())['data']
stock=sorted(stock,key=lambda r:r['date'])
spots={r['date'][:10]:r['price'] for r in stock}
rv={}
for i,r in enumerate(stock):
    day=r['date'][:10];rv[day]={}
    for n in [10,20,60]:
        if i>=n:
            ret=[math.log(stock[j]['price']/stock[j-1]['price']) for j in range(i-n+1,i+1)]
            rv[day][n]=statistics.stdev(ret)*math.sqrt(252)
expiry=date(2026,10,16)
metadata={r['symbol']:r for r in json.loads((ROOT/'research/byma_snapshot_20260907.json').read_text())['options']}
def pricing(s,k,t,r,q,v,side,n=200):
    if side=='call' and q==0:return bs_price(s,k,t,r,q,v,side)
    return binomial_price(s,k,t,r,q,v,n,side,'american')
def iv(p,s,k,t,r=.30,q=0,n=200,side='call'):
    # Lower bound keeps CRR risk-neutral probabilities within [0,1].
    lo=max(.0001,abs(r-q)*math.sqrt(t/n)*1.001);hi=5.
    a=pricing(s,k,t,r,q,lo,side,n);b=pricing(s,k,t,r,q,hi,side,n)
    if p<=a+.01 or p>=b:return None
    for _ in range(29):
        v=(lo+hi)/2
        if pricing(s,k,t,r,q,v,side,n)>p:hi=v
        else:lo=v
    return (lo+hi)/2
rows=[];counts=collections.Counter()
for ix,vals in enumerate(raw[1:],2):
    x=dict(zip(raw[0],vals));ticker=x['ticker'];side='call' if ticker[3]=='C' else 'put';k=float(re.search(r'[CV](\d+)OC$',ticker).group(1));day=x['date'][:10]
    s=spots.get(day);t=(expiry-date.fromisoformat(day)).days/365;p=x['price'];flags=[]
    if not x['volume']:flags.append('Zero reported volume')
    if not x['min']<=p<=x['max']:flags.append('Price outside daily range')
    intrinsic=max(s-k,0) if side=='call' else max(k-s,0)
    if p<intrinsic-.01:flags.append('Below intrinsic value')
    if ticker in metadata and metadata[ticker]['maturityDate']!=expiry.isoformat():raise ValueError('Expiry mismatch')
    v=None
    if not flags:
        v=iv(p,s,k,t,side=side)
        if v is None:flags.append('No stable model IV')
    counts.update(flags)
    greeks=bs_greeks(s,k,t,.30,0,v,side) if v else {}
    rows.append(dict(row=ix,date=day,ticker=ticker,side=side,k=k,p=p,volume=x['volume'],low=x['min'],high=x['max'],s=s,t=t,dte=round(t*365),intrinsic=intrinsic,timevalue=p-intrinsic,iv=v,delta=greeks.get('delta'),vega=greeks.get('vega',0)/100 if v else None,status='; '.join(flags) or 'Screen passed; indicative',raw=list(vals),close_formula=str(formulas[ix-1][4] or '')))
print('IV calculation complete',flush=True)
byday=collections.defaultdict(list)
for x in rows:byday[x['date']].append(x)
def interp_delta(xs,target):
    pairs=sorted((abs(x['delta']),x['iv']) for x in xs if x['iv'] is not None)
    for (a,va),(b,vb) in zip(pairs,pairs[1:]):
        if a<=target<=b and b>a:return va+(vb-va)*(target-a)/(b-a)
    return None
daily=[]
for day,xs in sorted(byday.items()):
    s=spots[day];passed=[x for x in xs if x['iv'] is not None]
    pairs={x['k']:{y['side']:y for y in passed if y['k']==x['k']} for x in passed}
    paired=[k for k,p in pairs.items() if len(p)==2 and abs(k/s-1)<=.08]
    k=min(paired,key=lambda k:abs(k/s-1)) if paired else None
    c=pairs[k]['call'] if k else None;p=pairs[k]['put'] if k else None
    atm=(c['iv']+p['iv'])/2 if c else None
    v20=(iv(c['p'],s,k,c['t'],.20,side='call')+iv(p['p'],s,k,p['t'],.20,side='put'))/2 if c else None
    v40=(iv(c['p'],s,k,c['t'],.40,side='call')+iv(p['p'],s,k,p['t'],.40,side='put'))/2 if c else None
    c25=interp_delta([x for x in passed if x['side']=='call'],.25);p25=interp_delta([x for x in passed if x['side']=='put'],.25)
    daily.append(dict(date=day,s=s,k=k,call_iv=c['iv'] if c else None,put_iv=p['iv'] if p else None,atm=atm,r20=v20,r40=v40,rv10=rv[day].get(10),rv20=rv[day].get(20),rv60=rv[day].get(60),call_vol=sum(x['volume'] for x in xs if x['side']=='call'),put_vol=sum(x['volume'] for x in xs if x['side']=='put'),call25=c25,put25=p25,valid=len(passed),total=len(xs),straddle=c['p']+p['p'] if c else None))
spread=[]
for day,xs in sorted(byday.items()):
    for side in ['call','put']:
        legs=sorted([x for x in xs if x['side']==side],key=lambda x:x['k'])
        for a,b,c in zip(legs,legs[1:],legs[2:]):
            width=b['k']-a['k']
            if abs(width-(c['k']-b['k']))>.001:continue
            cost=a['p']-2*b['p']+c['p']
            status='Indicative only'
            if any(x['iv'] is None for x in [a,b,c]):status='Flagged leg data'
            if not 0<cost<width:status='Outside standard debit bounds'
            spread.append(dict(date=day,type='Butterfly',side=side,k1=a['k'],k2=b['k'],k3=c['k'],p1=a['p'],p2=b['p'],p3=c['p'],row1=a['row'],row2=b['row'],row3=c['row'],cost=cost,width=width,status=status))
        for a,b in zip(legs,legs[1:]):
            long,short=(a,b) if side=='call' else (b,a)
            spread.append(dict(date=day,type='1x2 ratio',side=side,k1=long['k'],k2=short['k'],k3=None,p1=long['p'],p2=short['p'],p3=None,row1=long['row'],row2=short['row'],row3=None,cost=long['p']-2*short['p'],width=abs(a['k']-b['k']),status='Indicative only' if long['iv'] and short['iv'] else 'Flagged leg data'))
validation=[]
last=rows[-1]['date']
for x in [r for r in rows if r['date']==max(byday) and r['side']=='put' and r['iv'] and .9<r['k']/r['s']<1.1]:
    v400=iv(x['p'],x['s'],x['k'],x['t'],n=400,side='put')
    validation.append({'ticker':x['ticker'],'iv200':x['iv'],'iv400':v400,'difference':v400-x['iv']})
assert len(rows)==920 and len(set((x['date'],x['ticker']) for x in rows))==920
repricing=max(abs(pricing(x['s'],x['k'],x['t'],.3,0,x['iv'],x['side'])-x['p']) for x in rows if x['iv'])
assert repricing<.001
report={'rows':rows,'daily':daily,'spreads':spread,'stock':stock,'counts':dict(counts),'validation':validation,'reprice_max_error':repricing,'metadata_matches':sum(x['ticker'] in metadata for x in rows),'latest':max(byday)}
(OUT/'analysis.json').write_text(json.dumps(report,allow_nan=False))
print(json.dumps({'counts':dict(counts),'valid_iv':sum(x['iv'] is not None for x in rows),'latest':daily[-1],'spreads':len(spread),'validation':validation,'reprice_error':repricing},indent=2))
