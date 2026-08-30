'use client'
import {useEffect,useState} from 'react'
import {api,errorText,fmtDate,fmtId,fmtLift,fmtMoney,fmtNum,LoopRun,SystemStatus,EvidenceRecord} from '@/lib/api'

export function useStatus(){
  const[status,setStatus]=useState<SystemStatus|null>(null)
  const[error,setError]=useState('')
  useEffect(()=>{
    let timer:ReturnType<typeof setTimeout>;let alive=true
    const load=async()=>{try{const s=await api.status();if(alive)setStatus(s);timer=setTimeout(load,s.running_loop?4000:30000)}catch(e){if(alive)setError(errorText(e));timer=setTimeout(load,30000)}}
    load();return()=>{alive=false;clearTimeout(timer)}
  },[])
  return{status,error}
}

/* Shell and TopBar are now no-ops — Sidebar in layout.tsx handles navigation */
export function TopBar(){return null}
export function Shell({children}:{children:React.ReactNode}){return<>{children}</>}

export function PageHead({eyebrow,title,subtitle}:{eyebrow:string;title:string;subtitle:string}){
  return<div className="pagehead"><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{subtitle}</p></div>
}

export function Panel({title,children,action,tag}:{title:string;children:React.ReactNode;action?:React.ReactNode;tag?:string}){
  return<section className="panel"><div className="panel-head"><div className="panel-title">{title}{tag&&<span className="tag">{tag}</span>}</div>{action}</div>{children}</section>
}

export function Empty({children='No data yet'}:{children?:React.ReactNode}){return<div className="empty">{children}</div>}

export function Badge({children,tone='muted'}:{children:React.ReactNode;tone?:string}){return<span className={`badge ${tone}`}>{children}</span>}

export function Kpis({status}:{status:SystemStatus|null}){
  const b=status?.buffer,k=status?.kb,m=status?.model,r=status?.latest_run
  const data=[
    {label:'ATTACK FAMILIES TESTED',val:k?.total_families,delta:`${k?.simulatable_families??'—'} simulatable`,accent:'var(--blue)'},
    {label:'BUFFER PAYMENTS',val:b?.payment_records??'—',delta:`${b?.blocked??'—'} blocked · ${b?.bypassed??'—'} bypassed`,accent:'var(--red)'},
    {label:'ACTIVE MODEL',val:m?.version||'none',delta:m?.model_type||'No model loaded',accent:'var(--green)'},
    {label:'LATEST LOOP',val:r?.status||'—',delta:r?`${fmtId(r.id)}`:'',accent:'var(--orange)'},
    {label:'SCORE LIFT',val:fmtLift(r?.score_lift),delta:r?.verify_decision||'',accent:'var(--violet)'},
    {label:'KB SIGNALS',val:k?.total_signals,delta:`${k?.genai_load_bearing??0} genai load-bearing`,accent:'var(--blue)'},
  ]
  return<div className="kpis">{data.map(d=><div className="kpi" key={d.label} style={{'--accent':d.accent} as any}><span className="label">{d.label}</span><div className="val">{d.val??'—'}</div><div className="delta">{d.delta}</div></div>)}</div>
}

export function RunTable({runs}:{runs:LoopRun[]}){
  return<div className="tablewrap"><table><thead><tr><th>Started</th><th>Status</th><th>Trigger</th><th>Families</th><th>Buffer</th><th>Score Lift</th><th>Verify</th></tr></thead><tbody>{runs.map(r=><tr key={r.id}><td className="mono">{fmtDate(r.started_at)}</td><td><Badge tone={r.status}>{r.status}</Badge></td><td>{r.trigger||'—'}</td><td>{r.families_count??'—'}</td><td>{r.buffer_payments??'—'} / {r.buffer_bypassed??'—'}</td><td className="mono">{fmtLift(r.score_lift)}</td><td>{r.verify_decision||'—'}</td></tr>)}</tbody></table>{!runs.length&&<Empty>Awaiting completed loop run</Empty>}</div>
}

export function EvidenceTable({records,compact=false}:{records:EvidenceRecord[];compact?:boolean}){
  return<div className="tablewrap"><table><thead><tr><th>Time</th><th>Family</th><th>Step</th><th>Decision</th><th>Evasion</th><th>ML Score</th><th>Amount</th>{!compact&&<th>Hard negative</th>}</tr></thead><tbody>{records.map(e=><tr key={e.evidence_id}><td className="mono">{fmtDate(e.timestamp)}</td><td style={{fontFamily:'var(--font-space)',fontWeight:500}}>{e.attack_family}</td><td>{e.step??'—'}</td><td><Badge tone={e.sandbox_decision}>{e.sandbox_decision}</Badge></td><td>{e.evasion_outcome}</td><td className="mono">{fmtNum(e.ml_score)}</td><td className="mono">{fmtMoney(e.amount)}</td>{!compact&&<td>{e.is_hard_negative?'YES':'—'}</td>}</tr>)}</tbody></table>{!records.length&&<Empty>No evidence records yet</Empty>}</div>
}

export function RunSelector({runs,value,onChange}:{runs:LoopRun[];value:string;onChange:(v:string)=>void}){
  return<label className="selector">Run <select value={value} onChange={e=>onChange(e.target.value)}>{runs.map(r=><option value={r.id} key={r.id}>{fmtId(r.id)} · {r.status} · {fmtDate(r.started_at)}</option>)}</select></label>
}
