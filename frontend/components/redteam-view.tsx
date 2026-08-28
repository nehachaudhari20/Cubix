'use client'
import {useEffect,useMemo,useState} from 'react'
import {api, fmtId, fmtDate, LoopRun} from '@/lib/api'
import {Shell,PageHead,Panel,RunSelector,Badge,Empty} from './dashboard'

interface CampaignStep { title:string; description:string }
interface CampaignMemory { text:string; confidence:number }
interface CampaignEntry {
  id:string; family:string; family_name:string; status:string;
  novelty:number; stage:string; step:string;
  hypothesis:string; families_tags:string[];
  plan:CampaignStep[]; payload:Record<string,any>; memory:CampaignMemory[];
}
interface RedTeamViewData {
  campaigns:CampaignEntry[]; total_events:number; total_families:number;
  blocked_count:number; bypassed_count:number;
}

export function RedTeamView(){
  const[runs,setRuns]=useState<LoopRun[]>([])
  const[id,setId]=useState('')
  const[data,setData]=useState<RedTeamViewData|null>(null)
  const[selectedFamily,setSelectedFamily]=useState('')
  const[tab,setTab]=useState<'hyp'|'plan'|'payload'|'mem'>('hyp')
  const[loading,setLoading]=useState(false)
  const[err,setErr]=useState('')

  const completedRuns=useMemo(()=>runs.filter(r=>r.status==='completed'),[runs])

  useEffect(()=>{api.runs(30).then(setRuns).catch(e=>setErr(e.message))},[])
  useEffect(()=>{if(!id&&completedRuns.length)setId(completedRuns[0].id)},[completedRuns,id])

  useEffect(()=>{
    if(!id)return
    setLoading(true)
    api.redteamView(id).then(d=>{setData(d);if(d.campaigns.length)setSelectedFamily(d.campaigns[0].family)}).catch(e=>setErr(e.message)).finally(()=>setLoading(false))
  },[id])

  const selected=data?.campaigns.find(c=>c.family===selectedFamily)||data?.campaigns[0]||null

  return<Shell>
    <PageHead eyebrow="Red Team / Campaign" title="Red Team" subtitle="Threat Hunter → Planner → Generator → Memory. How the system discovers, plans, and adapts attacks."/>

    {err&&<div style={{background:'#fef2f2',border:'1px solid #fecaca',borderRadius:8,padding:12,marginBottom:16,fontSize:12,color:'var(--red)'}}>⚠ {err}</div>}

    {/* KPIs */}
    <div className="kpis" style={{gridTemplateColumns:'repeat(4,1fr)'}}>
      <div className="kpi"><span className="label">CAMPAIGNS</span><div className="val">{data?.total_families||0}</div><div className="delta">{data?.total_events||0} total events</div></div>
      <div className="kpi"><span className="label">BLOCKED</span><div className="val">{data?.blocked_count||0}</div><div className="delta">{data?.total_events?Math.round((data.blocked_count/data.total_events)*100):0}% block rate</div></div>
      <div className="kpi"><span className="label">BYPASSED</span><div className="val">{data?.bypassed_count||0}</div><div className="delta">{data?.total_events?Math.round((data.bypassed_count/data.total_events)*100):0}% bypass</div></div>
      <div className="kpi"><span className="label">NOVELTY</span><div className="val">{selected?.novelty?.toFixed(2)||'—'}</div><div className="delta">selected campaign</div></div>
    </div>

    {/* Main layout: campaign list + detail */}
    <div className="grid-left">
      {/* Campaign list sidebar */}
      <div className="panel">
        <div className="panel-title" style={{marginBottom:12}}>
          Loop run
          <div style={{marginLeft:'auto'}}>{completedRuns.length?<RunSelector runs={completedRuns} value={id} onChange={setId}/>:null}</div>
        </div>
        {loading?<Empty>Loading…</Empty>:null}
        <div className="camp-list">
          {(data?.campaigns||[]).map(c=><div key={c.family} className={`camp-row ${c.family===selectedFamily?'active':''}`} onClick={()=>setSelectedFamily(c.family)}>
            <div className="top"><span className="fam">{c.family_name}</span><Badge tone={c.status}>{c.status}</Badge></div>
            <div style={{fontSize:11,color:'var(--muted)',marginTop:2}}>{c.step} steps · novelty {c.novelty.toFixed(2)}</div>
            <div className="meta" style={{marginTop:4}}><span>{c.stage}</span></div>
          </div>)}
        </div>
      </div>

      {/* Detail panel with tabs */}
      <div className="panel">
        <div className="detail-tabs">
          <button className={`dtab ${tab==='hyp'?'active':''}`} onClick={()=>setTab('hyp')}>Hypothesis</button>
          <button className={`dtab ${tab==='plan'?'active':''}`} onClick={()=>setTab('plan')}>Plan Steps</button>
          <button className={`dtab ${tab==='payload'?'active':''}`} onClick={()=>setTab('payload')}>Payload</button>
          <button className={`dtab ${tab==='mem'?'active':''}`} onClick={()=>setTab('mem')}>Memory Used</button>
        </div>

        {!selected?<Empty>Select a campaign.</Empty>:<>
          {/* Hypothesis */}
          {tab==='hyp'&&<>
            <div className="section-title">Threat Hunter Reasoning</div>
            <div className="hyp-box">{selected.hypothesis}</div>
            <div className="chips" style={{marginTop:10}}>
              {selected.families_tags.map(t=><span key={t} className="chip-inner">{t}</span>)}
            </div>
          </>}

          {/* Plan Steps */}
          {tab==='plan'&&<>
            <div className="section-title">Attack Plan · {selected.plan.length} steps</div>
            <div className="steps">
              {selected.plan.map((s,i)=><div key={i} className="step">
                <div className="num">{i+1}</div>
                <div className="body"><div className="title">{s.title}</div><div className="desc">{s.description}</div></div>
              </div>)}
            </div>
          </>}

          {/* Payload */}
          {tab==='payload'&&<>
            <div className="section-title">Generated Action Payload</div>
            <pre>{JSON.stringify(selected.payload,null,2)}</pre>
          </>}

          {/* Memory */}
          {tab==='mem'&&<>
            <div className="section-title">Memory Consulted</div>
            {selected.memory.map((m,i)=><div key={i} className="mem-row">
              <span className="txt">{m.text}</span>
              <span className="conf">conf {m.confidence.toFixed(2)}</span>
            </div>)}
          </>}
        </>}
      </div>
    </div>
  </Shell>
}
