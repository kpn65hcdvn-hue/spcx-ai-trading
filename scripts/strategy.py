"""Research-only, completed-bar multi-timeframe signals and exploratory backtest.
No order endpoints. A signal is NOT a recommendation to trade.
"""
import datetime as dt
import math

def ema(values, period):
    if len(values)<period or any(not math.isfinite(x) for x in values): return None
    k=2/(period+1)
    result=sum(values[:period])/period
    for x in values[period:]: result=k*x+(1-k)*result
    return result

def rsi(values, period=14):
    if len(values)<period+1:return None
    changes=[values[i]-values[i-1] for i in range(1,len(values))]
    g=sum(max(x,0) for x in changes[-period:])/period
    l=sum(max(-x,0) for x in changes[-period:])/period
    if l==0:return 100. if g else 50.
    return 100-100/(1+g/l)

def read_frame(rows, period_secs, now_seconds):
    """Filter in-progress (bar time is opening timestamp) and invalid rows."""
    clean=[]
    for x in rows:
        try:
            ts=int(x['time']); close=float(x['close']); vol=float(x['vol'])
            high=float(x['high']);low=float(x['low']);opening=float(x['open'])
            if not all(math.isfinite(z) for z in (close,opening,vol,high,low)) or close<=0 or opening<=0 or vol<0 or high<low or not(low<=opening<=high and low<=close<=high):continue
            if ts+period_secs>now_seconds:continue
            clean.append({'time':ts,'close':close,'open':opening,'vol':vol,'high':high,'low':low})
        except (KeyError,TypeError,ValueError,OverflowError):continue
    return sorted({x['time']:x for x in clean}.values(),key=lambda x:x['time'])

def evaluate(rows):
    if len(rows)<35:return {'state':'insufficient','reason':'已收盘K线不足35根','count':len(rows)}
    close=[x['close'] for x in rows]
    a=ema(close,10);b=ema(close,25);r=rsi(close)
    avg=sum(x['vol'] for x in rows[-21:-1])/20
    vr=rows[-1]['vol']/avg if avg>0 else None
    label='观望';reason='趋势、动量或放量条件不同时满足'
    # Deliberately conservative, closed-candle only
    if a>b and 50<=r<70 and vr is not None and vr>=1.2:
        label='偏多观察';reason='EMA10>EMA25、RSI 50-70且最近完整K线量比≥1.2'
    elif a<b and 30<r<=50 and vr is not None and vr>=1.2:
        label='偏空观察';reason='EMA10<EMA25、RSI 30-50且最近完整K线量比≥1.2'
    return {'state':'ok','label':label,'reason':reason,'ema10':round(a,4),'ema25':round(b,4),'rsi14':round(r,2),'volume_ratio':round(vr,3) if vr is not None else None,'count':len(rows),'last_closed_at':dt.datetime.fromtimestamp(rows[-1]['time'],dt.timezone.utc).isoformat()}

def backtest(rows, fee_bps=10.0, slippage_bps=5.0, funding_bps_per_bar=0.0):
    """Exploratory one-bar study: signal at bar i close, next bar open entry,
    next bar close exit. Chronological, no lookahead in signals.
    Both sides fees/slippage are modeled, plus funding sensitivity per bar.
    No actual fills, leverage, margin, liquidation, or path-dependent stops.
    """
    if len(rows)<70:
        return {'status':'insufficient','message':'完整K线不足70根','bars':len(rows),'trades':0}
    for v in (fee_bps,slippage_bps,funding_bps_per_bar):
        if not math.isfinite(v) or v<0: raise ValueError('测试成本必须为非负有限数')
    eq=1.;peak=1.;dd=0.;trades=0;wins=0;net_returns=[]
    cost=(2*fee_bps+2*slippage_bps+funding_bps_per_bar)/10000
    for i in range(35,len(rows)-1):
        sig=evaluate(rows[:i+1]);side=1 if sig.get('label')=='偏多观察' else -1 if sig.get('label')=='偏空观察' else 0
        if not side: continue
        nxt=rows[i+1]
        gross=side*(nxt['close']/nxt['open']-1)
        net=gross-cost
        eq*=max(0.000001,1+net)
        peak=max(peak,eq);dd=max(dd,(peak-eq)/peak)
        net_returns.append(net);trades+=1;wins+=int(net>0)
    return {'status':'insufficient' if trades<30 else 'exploratory', 'bars':len(rows),'trades':trades,
            'win_rate_pct':round(100*wins/trades,2) if trades else None,
            'total_return_pct':round(100*(eq-1),2),'max_drawdown_pct':round(dd*100,2),
            'fee_per_side_bps':fee_bps,'slippage_per_side_bps':slippage_bps,
            'funding_sensitivity_bps_per_trade':funding_bps_per_bar,
            'model':'信号K线收盘判定，下一根开盘入场、同根收盘退出；每个信号独立持有一根',
            'message':'仅探索性回测。成本为假设值，不代表 HTX 实际费率；未模拟滑点尾部风险、强平、最小订单和资金费率结算时点。少于30笔或历史不足不可据此交易。'}

def combine(frames):
    labels=[frames[k].get('label') for k in ('15m','1h','4h')]
    if any(frames[k].get('state')!='ok' for k in ('15m','1h','4h')):
        return {'label':'数据不足','reason':'至少一个周期缺少足够已收盘K线'}
    if all(x=='偏多观察' for x in labels):return {'label':'多周期偏多候选','reason':'三个周期独立满足规则；不是交易指令'}
    if all(x=='偏空观察' for x in labels):return {'label':'多周期偏空候选','reason':'三个周期独立满足规则；不是交易指令'}
    return {'label':'观望','reason':'三个周期的趋势/成交量条件未形成一致信号'}
