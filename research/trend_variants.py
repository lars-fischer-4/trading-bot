import pandas as pd, numpy as np
def L(c):
    d=pd.read_feather(f'/tmp/claude-0/combo/data/{c}_EUR-4h.feather').set_index('date')['close']; return d
H=pd.DataFrame({c:L(c) for c in ['BTC','ETH']}).dropna()
R=H.pct_change().fillna(0); fee=0.0025
def run(name,pos):
    out=[]
    for c in H:
        p=pos[c].fillna(0); r=p.shift(1)*R[c]-p.diff().abs().fillna(0)*fee
        out.append(r)
    pr=sum(out)/2; eq=(1+pr).cumprod()
    s=lambda a,b: eq[(eq.index>=a)&(eq.index<b)]
    yr={y:(s(f'{y}-01-01',f'{y+1}-01-01').iloc[-1]/s(f'{y}-01-01',f'{y+1}-01-01').iloc[0]-1)*100 for y in (2023,2024,2025,2026)}
    print(f'{name:40s} '+' '.join(f'{y}:{v:+6.1f}%' for y,v in yr.items())+f'  maxDD {100*(eq/eq.cummax()-1).min():.0f}%  trades {int(pos.diff().abs().sum().sum())}')
st=H.index>='2023-03-01'
def band(n,b):
    sma=H.rolling(n).mean(); p=pd.DataFrame(np.nan,index=H.index,columns=H.columns)
    p[H>sma*(1+b)]=1; p[H<sma*(1-b)]=0; return p.ffill().fillna(0)
for n,b in ((300,0.02),(300,0.0),(180,0.02),(120,0.02)): run(f'SMA{n} (4h) band {b}  [ComboV1: 300/0.02]', band(n,b)[st])
for f,s in ((5,20),(10,40),(20,100),(10,30)):
    p=(H.ewm(span=f*6).mean()>H.ewm(span=s*6).mean()).astype(float); run(f'EMA {f}/{s} Tage', p[st])
run('Halten',pd.DataFrame(1.0,index=H.index,columns=H.columns)[st])
