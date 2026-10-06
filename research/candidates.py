import pandas as pd, numpy as np
D='/tmp/claude-0/dt/data'
TOP=['BTC','ETH','XRP','SOL','ADA','SUI','DOGE','LINK','FET','TAO']
TOP20=TOP+['MOODENG','WIF','HYPE','PEPE','HBAR','ONDO','XLM','NEAR','LTC','AVAX']
def load(c):
    d=pd.read_feather(f'{D}/{c}_EUR-1h.feather').set_index('date')['close']
    return d[~d.index.duplicated()]
H=pd.DataFrame({c:load(c) for c in TOP20}).sort_index().ffill()
H=H[H.index>='2025-01-20']
R=H.pct_change().fillna(0)
def report(name, w, fee=0.0025, freq='h'):
    # w: target weights (rows=time, cols=coins), applied to next period's return
    w=w.fillna(0)
    turn=w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1))
    rets=R if freq=='h' else Rd
    pr=(w.shift(1)*rets.reindex(w.index)).sum(axis=1)-turn.shift(1).fillna(0)*fee
    eq=(1+pr).cumprod()
    y25=eq[eq.index<'2026-01-01'].iloc[-1]-1; y26=eq.iloc[-1]/eq[eq.index<'2026-01-01'].iloc[-1]-1
    dd=(eq/eq.cummax()-1).min()
    print(f'{name:55s} total {100*(eq.iloc[-1]-1):+7.1f}%  2025 {100*y25:+6.1f}%  2026 {100*y26:+6.1f}%  maxDD {100*dd:6.1f}%  turnover/day {turn.sum()/623:.2f}')
# Benchmark
Hd=H.resample('1D').last(); Rd=Hd.pct_change().fillna(0)
report('Halten: gleich gewichtet top10 (taeglich)', pd.DataFrame(0.1,index=Hd.index,columns=TOP).reindex(columns=TOP20).fillna(0), fee=0, freq='d')
report('Halten: BTC', pd.DataFrame({'BTC':1.0},index=Hd.index).reindex(columns=TOP20).fillna(0), fee=0, freq='d')
# A: Stunden-Saisonalitaet, BTC 21-23 UTC
for coins in (['BTC'],['BTC','ETH']):
  for fee in (0.0025,0.0015):
    w=pd.DataFrame(0.0,index=H.index,columns=TOP20)
    hrs=H.index.hour
    for c in coins: w.loc[(hrs>=21)&(hrs<23),c]=1/len(coins)
    report(f'A Stunden 21-23 UTC {"+".join(coins)} fee {fee}', w, fee)
# A2: Wochenende
w=pd.DataFrame(0.0,index=H.index,columns=TOP20); w.loc[H.index.dayofweek>=5,'BTC']=1
report('A2 BTC nur am Wochenende', w)
# B: Zeitreihen-Momentum EMA, taeglich, Volatilitaets-normiert
for coins,tag in ((TOP,'top10'),(['BTC','ETH'],'BTC+ETH'),(TOP20,'top20')):
  for f,s in ((10,40),(20,100),(5,20)):
    up=(Hd[coins].ewm(span=f).mean()>Hd[coins].ewm(span=s).mean()).astype(float)
    vol=Rd[coins].rolling(30).std()*np.sqrt(365)
    raw=up*(0.5/vol).clip(upper=1)        # Ziel 50 % Jahresvola pro Coin
    w=raw.div(len(coins))
    report(f'B TS-Momentum EMA{f}/{s} vol-norm {tag}', w.reindex(columns=TOP20).fillna(0), freq='d')
    report(f'B TS-Momentum EMA{f}/{s} gleich {tag}', (up/len(coins)).reindex(columns=TOP20).fillna(0), freq='d')
# C: Querschnitt-Momentum, woechentlich top-k nach 7/28-Tage-Rendite
for coins,tag in ((TOP,'top10'),(TOP20,'top20')):
  for lb in (7,28):
    for k in (2,3):
      mom=Hd[coins].pct_change(lb)
      wk=mom.resample('W').last()
      sel=wk.rank(axis=1,ascending=False)<=k
      w=(sel.astype(float)/k).reindex(Hd.index,method='ffill').shift(1)
      report(f'C Querschnitt top{k} nach {lb}T, woechentl. {tag}', w.reindex(columns=TOP20).fillna(0), freq='d')
      # mit Filter: nur wenn BTC ueber 50T-Schnitt
      f=(Hd['BTC']>Hd['BTC'].rolling(50).mean()).astype(float)
      report(f'C  + BTC-Trendfilter', w.reindex(columns=TOP20).fillna(0).mul(f,axis=0), freq='d')
# D: Donchian-Ausbruch 20/10 Tage
for coins,tag in ((TOP,'top10'),(['BTC','ETH'],'BTC+ETH')):
  for n,m in ((20,10),(55,20)):
    hi=Hd[coins].rolling(n).max().shift(1); lo=Hd[coins].rolling(m).min().shift(1)
    pos=pd.DataFrame(np.nan,index=Hd.index,columns=coins)
    pos[Hd[coins]>hi]=1; pos[Hd[coins]<lo]=0
    pos=pos.ffill().fillna(0)
    report(f'D Donchian {n}/{m} {tag}', (pos/len(coins)).reindex(columns=TOP20).fillna(0), freq='d')
# E: Kurzfrist-Umkehr: taeglich die k schlechtesten Coins des Vortags kaufen, 1 Tag halten
for coins,tag in ((TOP,'top10'),(TOP20,'top20')):
  for k in (1,2):
    sel=Rd[coins].rank(axis=1)<=k
    report(f'E Verlierer des Vortags top{k} {tag}', (sel.astype(float)/k).reindex(columns=TOP20).fillna(0), freq='d')
# F: ETH/BTC-Verhaeltnis Mean Reversion (z-score 30T)
ratio=np.log(Hd['ETH']/Hd['BTC']); z=(ratio-ratio.rolling(30).mean())/ratio.rolling(30).std()
pos=pd.Series(np.nan,index=Hd.index); pos[z<-1.5]=1; pos[z>0]=0; pos=pos.ffill().fillna(0)
w=pd.DataFrame(0.0,index=Hd.index,columns=TOP20); w['ETH']=pos; w['BTC']=1-pos
report('F ETH/BTC Umschichten nach z-Score (immer investiert)', w, freq='d')
