#!/usr/bin/env python3
"""Public-market-only updater. No account API keys or trade endpoints."""
import datetime as dt
import json
import math
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
UTC = dt.timezone.utc
NOW = dt.datetime.now(UTC).isoformat(timespec='seconds').replace('+00:00','Z')


def get(url, params):
    uri = url + '?' + urlencode(params)
    req = Request(uri, headers={'User-Agent':'SPCX-AI-V2-educational/1.0', 'Accept':'application/json'})
    with urlopen(req, timeout=16) as r:
        return json.load(r)


def save(name, obj):
    (DATA/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n',encoding='utf-8')


def finite(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):
        return None


def market():
    out={'source':'HTX public USDT-margined swaps','symbol':'SPCX-USDT','fetched_at':NOW,'status':'unavailable', 'message':'尚未验证 HTX SPCX-USDT 公共行情接口','last_price':None,'open_24h':None,'high_24h':None,'low_24h':None,'volume_24h':None,'candles':[]}
    base='https://api.hbdm.com'
    try:
        # Validate contract identity; never substitute a different exchange or instrument.
        info=get(base+'/linear-swap-api/v1/swap_contract_info', {'contract_code':'SPCX-USDT'})
        contracts=info.get('data', []) if isinstance(info,dict) else []
        if not isinstance(contracts,list): contracts=[contracts]
        valid=any(isinstance(x,dict) and str(x.get('contract_code','')).upper()=='SPCX-USDT' for x in contracts)
        if not valid:
            raise ValueError('HTX 合约目录中未确认 SPCX-USDT；可能是不同交易分区或合约已变更')
        ticker=get(base+'/linear-swap-ex/market/detail/merged',{'contract_code':'SPCX-USDT'})
        t=ticker.get('tick',{}) if isinstance(ticker,dict) else {}
        if ticker.get('status')!='ok' or not isinstance(t,dict): raise ValueError('HTX 行情响应无效')
        candles=get(base+'/linear-swap-ex/market/history/kline',{'contract_code':'SPCX-USDT','period':'60min','size':100})
        c=candles.get('data',[]) if isinstance(candles,dict) else []
        rows=[]
        if isinstance(c,list):
            for k in c:
                if not isinstance(k,dict):continue
                price=finite(k.get('close')); ts=k.get('id')
                if price is None or not isinstance(ts,(int,float)):continue
                rows.append({'time':int(ts),'open':finite(k.get('open')),'high':finite(k.get('high')),'low':finite(k.get('low')),'close':price,'vol':finite(k.get('vol'))})
        rows.sort(key=lambda k:k['time'])
        close=finite(t.get('close'))
        if close is None or close <= 0: raise ValueError('HTX 报价不是有效正数')
        out.update({'status':'ok','message':'官方公开行情；非推送实时流，按后台定时更新','last_price':close,'open_24h':finite(t.get('open')),'high_24h':finite(t.get('high')),'low_24h':finite(t.get('low')),'volume_24h':finite(t.get('vol')),'candles':rows})
        # HTX may return contract size via contract info. Do not infer if absent.
        contract=next(x for x in contracts if isinstance(x,dict) and str(x.get('contract_code','')).upper()=='SPCX-USDT')
        out['contract_size']=finite(contract.get('contract_size'))
    except Exception as e:
        out['message']=str(e)[:220]
    save('market.json',out)
    return out


def news():
    out={'source':'Spaceflight News API / third-party aggregated headlines','fetched_at':NOW,'status':'unavailable','message':'未获取到新闻','articles':[]}
    try:
        response=get('https://api.spaceflightnewsapi.net/v4/articles/',{'search':'SpaceX','limit':20,'ordering':'-published_at'})
        items=response.get('results',[]) if isinstance(response,dict) else []
        articles=[]
        for i in items:
            if not isinstance(i,dict):continue
            url=str(i.get('url') or '')
            if not url.startswith(('https://','http://')): continue
            articles.append({'title':str(i.get('title') or '')[:240], 'url':url, 'source':str(i.get('news_site') or '来源未标记')[:80], 'published_at':i.get('published_at'), 'summary':str(i.get('summary') or '')[:500]})
        out.update({'status':'ok' if articles else 'empty','message':'新闻是第三方聚合，未自动核实真实性或利好利空','articles':articles[:20]})
    except Exception as e:
        out['message']='新闻接口失败: '+str(e)[:200]
    save('news.json',out)
    return out

if __name__=='__main__':
    m=market();n=news()
    print('market:',m['status'],m['message'])
    print('news:',n['status'],len(n['articles']),n['message'])
