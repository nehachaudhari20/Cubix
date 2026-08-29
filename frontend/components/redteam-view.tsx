'use client'
import {useEffect,useMemo,useState} from 'react'
import {api, fmtId, fmtDate, LoopRun} from '@/lib/api'
import {PageHead,Panel,RunSelector,Badge,Empty} from './dashboard'

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
  const[kbFamilies,setKbFamilies]=useState<any[]>([])
  const[selectedFamily,setSelectedFamily]=useState('')
  const[tab,setTab]=useState<'hyp'|'plan'|'payload'|'mem'>('hyp')
  const[loading,setLoading]=useState(false)
  const[err,setErr]=useState('')

  const completedRuns=useMemo(()=>runs.filter(r=>r.status==='completed'),[runs])

  useEffect(()=>{api.runs(30).then(setRuns).catch(e=>setErr(e.message))},[])
  useEffect(()=>{if(!id&&completedRuns.length)setId(completedRuns[0].id)},[completedRuns,id])

  // Load KB families from the backend
  useEffect(()=>{
    fetch((process.env.NEXT_PUBLIC_API_BASE_URL||'http://localhost:8000')+'/api/kb/stats')
      .then(r=>r.json())
      .then(d=>{
        // Get all family IDs from simulatable_ids
        const ids = d.simulatable_ids || []
        // Fetch each family detail
        return Promise.all(ids.slice(0,20).map((fid:string)=>
          fetch((process.env.NEXT_PUBLIC_API_BASE_URL||'http://localhost:8000')+'/api/kb/families/'+encodeURIComponent(fid))
            .then(r=>r.json()).catch(()=>null)
        ))
      })
      .then(families=>{
        setKbFamilies(families.filter(Boolean))
      })
      .catch(()=>{})
  },[])

  useEffect(()=>{
    if(!id)return
    setLoading(true)
    api.redteamView(id).then(d=>{
      setData(d)
      if(d.campaigns.length)setSelectedFamily(d.campaigns[0].family)
    }).catch(e=>setErr(e.message)).finally(()=>setLoading(false))
  },[id])

  const selected=data?.campaigns.find(c=>c.family===selectedFamily)||data?.campaigns[0]||null

  // Combine KB families with campaign families for the selector
  const allFamilies = useMemo(()=>{
    const kbMap = new Map<string,any>()
    kbFamilies.forEach(f=>kbMap.set(f.attack_id||f.id, f))
    // Add campaign families too
    ;(data?.campaigns||[]).forEach(c=>{
      if(!kbMap.has(c.family)){
        kbMap.set(c.family, {attack_id:c.family, name:c.family_name, lifecycle_stage:c.stage})
      }
    })
    return [...kbMap.values()].sort((a,b)=>(a.attack_id||'').localeCompare(b.attack_id||''))
  },[kbFamilies, data])

  return(
    <div style={{padding:'22px 28px 0'}}>
      <PageHead eyebrow="Red Team / Campaign" title="Red Team" subtitle="Threat Hunter -> Planner -> Generator -> Memory. How the system discovers, plans, and adapts attacks."/>

      {err&&<div style={{background:'#fef2f2',border:'1px solid #fecaca',borderRadius:8,padding:12,marginBottom:16,fontSize:12,color:'#dc2626'}}>{err}</div>}

      {/* KPIs */}
      <div className="kpis" style={{gridTemplateColumns:'repeat(4,1fr)'}}>
        <div className="kpi"><span className="label">CAMPAIGNS</span><div className="val">{data?.total_families||0}</div><div className="delta">{data?.total_events||0} total events</div></div>
        <div className="kpi"><span className="label">BLOCKED</span><div className="val">{data?.blocked_count||0}</div><div className="delta">{data?.total_events?Math.round((data.blocked_count/data.total_events)*100):0}% block rate</div></div>
        <div className="kpi"><span className="label">BYPASSED</span><div className="val">{data?.bypassed_count||0}</div><div className="delta">{data?.total_events?Math.round((data.bypassed_count/data.total_events)*100):0}% bypass</div></div>
        <div className="kpi"><span className="label">NOVELTY</span><div className="val">{selected?.novelty?.toFixed(2)||'--'}</div><div className="delta">selected campaign</div></div>
      </div>

      {/* Family Selector - full KB families */}
      <div className="panel" style={{marginBottom:16}}>
        <div className="panel-title">Attack Family Selector <span className="tag">{allFamilies.length} families in KB</span></div>
        <div style={{display:'flex',gap:12,alignItems:'center',flexWrap:'wrap'}}>
          <select
            value={selectedFamily}
            onChange={e=>setSelectedFamily(e.target.value)}
            style={{flex:1,minWidth:300,padding:'10px 14px',borderRadius:8,border:'1px solid #e5e7eb',background:'#f9fafb',color:'#111827',fontSize:13}}
          >
            <option value="">Select attack family from KB...</option>
            {allFamilies.map(f=>(
              <option key={f.attack_id||f.id} value={f.attack_id||f.id}>
                {f.attack_id||f.id} -- {f.name||f.family_name||''}
                {f.lifecycle_stage ? ` [${f.lifecycle_stage}]` : ''}
              </option>
            ))}
          </select>
          {completedRuns.length>0 && (
            <div style={{fontSize:12,color:'#6b7280'}}>
              Run: <RunSelector runs={completedRuns} value={id} onChange={setId}/>
            </div>
          )}
        </div>
        {selectedFamily && kbFamilies.find(f=>(f.attack_id||f.id)===selectedFamily) && (
          <div style={{marginTop:12,padding:'12px 16px',background:'#f9fafb',border:'1px solid #e5e7eb',borderRadius:10}}>
            {(()=>{
              const fam = kbFamilies.find(f=>(f.attack_id||f.id)===selectedFamily)
              return fam ? (
                <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:12}}>
                  <div><div style={{fontSize:10,color:'#6b7280',textTransform:'uppercase'}}>Stage</div><div style={{fontSize:13,fontWeight:600}}>{fam.lifecycle_stage||'--'}</div></div>
                  <div><div style={{fontSize:10,color:'#6b7280',textTransform:'uppercase'}}>Simulation</div><div style={{fontSize:13,fontWeight:600}}>{fam.simulation_type||'--'}</div></div>
                  <div><div style={{fontSize:10,color:'#6b7280',textTransform:'uppercase'}}>Variants</div><div style={{fontSize:13,fontWeight:600}}>{fam.variants?.length||0}</div></div>
                  <div><div style={{fontSize:10,color:'#6b7280',textTransform:'uppercase'}}>Signals</div><div style={{fontSize:13,fontWeight:600}}>{fam.detection_signals?.length||0}</div></div>
                </div>
              ) : null
            })()}
          </div>
        )}
      </div>

      {/* Main layout: campaign list + detail */}
      <div className="grid-left">
        {/* Campaign list sidebar */}
        <div className="panel">
          <div className="panel-title" style={{marginBottom:12}}>
            Campaign Results
          </div>
          {loading?<Empty>Loading...</Empty>:null}
          {!data?.campaigns?.length && !loading && <Empty>No campaign data for this run.</Empty>}
          <div className="camp-list">
            {(data?.campaigns||[]).map(c=><div key={c.family} className={`camp-row ${c.family===selectedFamily?'active':''}`} onClick={()=>setSelectedFamily(c.family)}>
              <div className="top"><span className="fam">{c.family_name}</span><Badge tone={c.status}>{c.status}</Badge></div>
              <div style={{fontSize:11,color:'var(--muted)',marginTop:2}}>{c.step} steps -- novelty {c.novelty.toFixed(2)}</div>
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

          {!selected?<Empty>Select a campaign from the list or KB family above.</Empty>:<>
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
              <div className="section-title">Attack Plan -- {selected.plan.length} steps</div>
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
              <pre style={{background:'#f9fafb',border:'1px solid #e5e7eb',borderRadius:8,padding:14,fontSize:12,overflow:'auto'}}>{JSON.stringify(selected.payload,null,2)}</pre>
            </>}

            {/* Memory */}
            {tab==='mem'&&<>
              <div className="section-title">Memory Consulted</div>
              {selected.memory.map((m,i)=><div key={i} className="mem-row">
                <span className="txt">{m.text}</span>
                <span className="conf">conf {m.confidence.toFixed(2)}</span>
              </div>)}
              {!selected.memory.length && <Empty>No memory entries for this campaign.</Empty>}
            </>}
          </>}
        </div>
      </div>
    </div>
  )
}
