from pathlib import Path
import json, urllib.request, urllib.parse, datetime

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
env={}
for line in (ROOT/'.env.ppi').read_text().splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        k,v=line.split('=',1);env[k.strip()]=v.strip().strip('\"').strip("'")
base='https://clientapi.portfoliopersonal.com/api/1.0/'
h={'AuthorizedClient':env.get('PPI_AUTHORIZED_CLIENT') or 'API_CLI_PYTHON','ClientKey':env.get('PPI_CLIENT_KEY') or 'pp19PythonApp12','ApiKey':env['PPI_API_KEY'],'ApiSecret':env['PPI_API_SECRET']}
if True:
    h['Content-Type']='application/json'
    req=urllib.request.Request(base+'Account/LoginApi',headers=h,data=b'',method='POST')
    with urllib.request.urlopen(req,timeout=30) as r: auth=json.load(r)
    auth=auth[0] if isinstance(auth,list) else auth
    h={k:v for k,v in h.items() if k not in ['ApiKey','ApiSecret']}
    h['Authorization']='Bearer '+auth['accessToken']
    params=dict(ticker='GGAL',type='ACCIONES',settlement='A-24HS',dateFrom='2026-06-01T00:00:00',dateTo='2026-09-16T23:59:59')
    req=urllib.request.Request(base+'MarketData/Search?'+urllib.parse.urlencode(params),headers=h)
    with urllib.request.urlopen(req,timeout=40) as r: d=json.load(r)
    (OUT/'ppi_stock_raw.json').write_text(json.dumps({'params':params,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'data':d},indent=2))
    print('PPI share observations',len(d),'first',d[0].get('date'),'last',d[-1].get('date'))
