#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,logging,os,re,sys,tempfile,time
from dataclasses import dataclass
from pathlib import Path
logging.basicConfig(level=logging.WARNING)
for _n in ('sentence_transformers','transformers','httpx','httpcore','huggingface_hub','filelock','tqdm'):
    logging.getLogger(_n).setLevel(logging.ERROR)
os.environ.setdefault('KMP_DUPLICATE_LIB_OK','TRUE')
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('TOKENIZERS_PARALLELISM','false')
REPO_ROOT=Path(__file__).resolve().parent.parent.parent
sys.path.insert(0,str(REPO_ROOT))
from slowave.core.config import SlowaveConfig
from slowave.core.engine import SlowaveEngine
from slowave.latent.replay_engine import ReplayConfig
from slowave.latent.retrieval import RetrievalConfig
from slowave.symbolic.encoder import EncoderConfig,TextEncoder
HIT=0.5
def ks(hyp,ans):
    stop={'the','a','an','is','was','were','are','i','my','me','it','its','of','in','on','at','to','for','and','or','that','this','with','be','have','has','had'}
    tok=lambda s:{w for w in re.findall(r'[a-z0-9]+',s.lower()) if w not in stop and (len(w)>1 or w.isdigit())}
    at=tok(ans)
    return len(at&tok(hyp))/len(at) if at else 0.0
@dataclass
class R:
    pid:str;name:str;q:str;ans:str;hyp:str;score:float;hit:bool;ns:int;ne:int;ti:float;tr:float;err:str|None=None
def run(persona,enc,top_k=5,thr=0.65):
    pid=persona['persona_id'];name=persona['name']
    with tempfile.NamedTemporaryFile(suffix='.db',delete=False) as f: db=f.name
    out=[]
    try:
        cfg=SlowaveConfig(db_path=db,dim=enc.dim,encoder=EncoderConfig(),
            replay=ReplayConfig(assignment_threshold=thr,sample_size=256,max_prototypes_per_replay=32),
            retrieval=RetrievalConfig(salience_weight=0.3,neighbor_top_k=6),disable_encoder=False)
        eng=SlowaveEngine(cfg,shared_encoder=enc)
        t0=time.time()
        for sess in persona['sessions']:
            sid=eng.session_start(agent='dmr',project=pid)
            for turn in sess:
                c=str(turn.get('content','')).strip()
                if not c: continue
                etype='user_message' if turn.get('role','user')=='user' else 'assistant_message'
                eng.event_append(session_id=sid,type=etype,content=c)
            eng.session_end(sid,consolidate=False)
        ti=round(time.time()-t0,2)
        eng.consolidate_once()
        for qa in persona['questions']:
            q=str(qa['question']);a=str(qa['answer'])
            t1=time.time()
            try:
                res=eng.recall(q,top_k=top_k,evidence=False)
                tr=round(time.time()-t1,4)
                sh=' '.join(s.content_text for s in res.schemas)
                eh=' '.join(ep['content_text'] for ep in res.episode_texts if ep['content_text'])
                hyp=(sh+' '+eh).strip()
                sc=ks(hyp,a)
                out.append(R(pid,name,q,a,hyp[:400],round(sc,3),sc>=HIT,len(res.schemas),len(res.episode_texts),ti,tr))
            except Exception as e:
                out.append(R(pid,name,q,a,'',0.0,False,0,0,ti,0.0,str(e)))
        eng.close()
    finally:
        for ext in ('','-wal','-shm'):
            p=db+ext
            if os.path.exists(p):
                try: os.remove(p)
                except: pass
    return out
def main():
    pa=argparse.ArgumentParser()
    pa.add_argument('--dataset',default='data/dmr/dmr.json')
    pa.add_argument('--top-k',type=int,default=5)
    pa.add_argument('--threshold',type=float,default=0.65)
    pa.add_argument('--out',default=None)
    args=pa.parse_args()
    dp=Path(args.dataset)
    if not dp.is_absolute(): dp=REPO_ROOT/dp
    if not dp.exists(): print('Not found:',dp,file=sys.stderr); sys.exit(1)
    personas=json.loads(dp.read_text())
    print('Loading dataset:',dp)
    nq=sum(len(p['questions']) for p in personas)
    print('Personas:',len(personas),'  Questions:',nq)
    print('Loading encoder... ',end='',flush=True)
    enc=TextEncoder(EncoderConfig()); _=enc.encode('warmup')
    print('OK (dim='+str(enc.dim)+')')
    print()
    all_r=[]; t_start=time.time()
    for i,persona in enumerate(personas,1):
        print('['+str(i)+'/'+str(len(personas))+'] '+persona['name']+' ...',end=' ',flush=True)
        t0=time.time()
        rs=run(persona,enc=enc,top_k=args.top_k,thr=args.threshold)
        el=time.time()-t0
        h=sum(r.hit for r in rs)
        print(str(h)+'/'+str(len(rs))+' ('+str(round(100*h/max(1,len(rs))))+'%)  '+str(round(el,1))+'s')
        all_r.extend(rs)
    et=time.time()-t_start
    tq=len(all_r);th=sum(r.hit for r in all_r);tp=100*th/max(1,tq)
    print()
    print('Completed',tq,'questions in',round(et,1),'s')
    print()
    print('='*66)
    print(' SLOWAVE - Deep Memory Retrieval (DMR)')
    print('='*66)
    by_p={}
    for r in all_r: by_p.setdefault(r.pid,[]).append(r)
    print(' Persona           N   Hits  Hit%')
    print(' '+'-'*14+'  '+'-'*3+'  '+'-'*4+'  '+'-'*5)
    for pid in sorted(by_p):
        rs=by_p[pid];h=sum(r.hit for r in rs);nm=rs[0].name
        print(' '+nm.ljust(14)+'  '+str(len(rs)).ljust(3)+'  '+str(h).ljust(4)+'  '+str(round(100*h/max(1,len(rs)),1))+'%')
    print(' '+'-'*14+'  '+'-'*3+'  '+'-'*4+'  '+'-'*5)
    print(' '+'TOTAL'.ljust(14)+'  '+str(tq).ljust(3)+'  '+str(th).ljust(4)+'  '+str(round(tp,1))+'%')
    print()
    print(' Published baselines (LLM-augmented, Zep paper arXiv:2501.13956):')
    print('   MemGPT: 93.4%   Zep: 94.8%')
    print('   Slowave: '+str(round(tp,1))+'%  (ZERO LLM calls, brain-only)')
    ar=sum(r.tr for r in all_r)/max(1,len(all_r))
    print(' Recall latency: ~'+str(round(ar*1000))+'ms/q   Cost: $0.00')
    misses=[r for r in all_r if not r.hit]
    if misses:
        print(' Sample misses ('+str(min(5,len(misses)))+' of '+str(len(misses))+')')
        for r in misses[:5]:
            print('   ['+r.name+'] Q: '+r.q)
            print('   A: '+r.ans+'  ks='+str(r.score))
    print('='*66)
    if args.out:
        o={'summary':{'total_hits':th,'total_questions':tq,'hit_pct':round(tp,2)},
           'results':[{'persona_id':r.pid,'persona_name':r.name,'question':r.q,'expected':r.ans,'hypothesis':r.hyp,'ks':r.score,'hit':r.hit} for r in all_r]}
        Path(args.out).write_text(json.dumps(o,indent=2))
        print('Results saved to:',args.out)
if __name__=='__main__': main()
