'use client'
import {useEffect,useMemo,useState} from 'react'
import {api, LoopRun} from '@/lib/api'
import {Badge,Empty} from './dashboard'

interface CampaignStep {
  title:string; description:string
  decision?:string|null; ml_score?:number|null; amount?:number|null; outcome?:string|null
}
interface CampaignMemory { text:string; confidence:number; source?:string; kind?:string }
interface ThreatIntelligence {
  summary:string
  objective?:string|null; attacker?:string|null; target?:string|null
  surface?:string|null; simulation_type?:string|null
  genai_classification?:string|null; evidence_confidence?:string|null
  prerequisites:string[]; attack_flow:string[]; variants:string[]
  controls_targeted:string[]; signals:{name?:string;signal_id?:string;detection_method?:string}[]
  technique_ids:string[]; reasoning?:string|null
}
interface CampaignEntry {
  id:string; family:string; family_name:string; status:string; executed:boolean
  novelty:number; stage:string; step:string
  event_count:number; blocked:number; bypassed:number; challenged:number
  mean_ml_score:number|null
  hypothesis:string; threat_intelligence:ThreatIntelligence
  families_tags:string[]; plan:CampaignStep[]
  payload:Record<string,any>; payloads:Record<string,any>[]
  memory:CampaignMemory[]; events:Record<string,any>[]
}
interface RedTeamViewData {
  loop_id:string; loop_status:string; families_tested:number
  campaigns:CampaignEntry[]; total_events:number; total_families:number
  executed_families:number; blocked_count:number; bypassed_count:number
  buffer_payments:number; score_lift:number|null; kb_family_count:number
}

function toneFor(status:string){
  const s=(status||'').toUpperCase()
  if(s==='SUCCEEDED'||s==='COMPLETED')return 'ALLOW'
  if(s==='BLOCKED'||s==='FAILED')return 'BLOCK'
  if(s==='CHALLENGED'||s==='RUNNING')return 'CHALLENGE'
  return 'muted'
}

function pickBestLoop(loops: LoopRun[]): string {
  const usable = loops.filter((r) => r.status === "completed" || r.status === "stopped")
  if (!usable.length) return loops[0]?.id || ""
  const scored = [...usable].sort((a, b) => {
    const liftA = a.score_lift ?? -999
    const liftB = b.score_lift ?? -999
    if (liftB !== liftA) return liftB - liftA
    const prA = a.val_pr_auc ?? -999
    const prB = b.val_pr_auc ?? -999
    if (prB !== prA) return prB - prA
    return String(b.started_at || "").localeCompare(String(a.started_at || ""))
  })
  return scored[0].id
}

export function RedTeamView({embedded=false}:{embedded?:boolean}){
  const[loops,setLoops]=useState<LoopRun[]>([])
  const[id,setId]=useState('')
  const[data,setData]=useState<RedTeamViewData|null>(null)
  const[kbFamilies,setKbFamilies]=useState<any[]>([])
  const[selectedFamily,setSelectedFamily]=useState('')
  const[tab,setTab]=useState<'hyp'|'plan'|'payload'|'mem'>('hyp')
  const[loading,setLoading]=useState(false)
  const[err,setErr]=useState('')
  const[familyFilter,setFamilyFilter]=useState('')

  useEffect(()=>{
    Promise.all([
      api.redteamLoops(40).catch(()=>api.runs(40)),
      api.families(200).catch(()=>[]),
    ]).then(([loopList, families])=>{
      const list = Array.isArray(loopList)?loopList:[]
      setLoops(list)
      setKbFamilies(Array.isArray(families)?families:[])
      if (!id && list.length) setId(pickBestLoop(list))
    }).catch(e=>setErr(e.message||String(e)))
  },[])

  useEffect(()=>{
    if(!id&&loops.length)setId(pickBestLoop(loops))
  },[loops,id])

  useEffect(()=>{
    if(!id)return
    setLoading(true)
    setErr('')
    api.redteamView(id).then(d=>{
      setData(d)
      const firstExec=d.campaigns?.find((c:CampaignEntry)=>c.executed)
      setSelectedFamily((firstExec||d.campaigns?.[0])?.family||'')
    }).catch(e=>setErr(e.message||String(e))).finally(()=>setLoading(false))
  },[id])

  const selected=data?.campaigns.find(c=>c.family===selectedFamily)||data?.campaigns[0]||null
  const ti=selected?.threat_intelligence

  const allFamilies=useMemo(()=>{
    const map=new Map<string,any>()
    kbFamilies.forEach(f=>map.set(f.attack_id||f.id,f))
    ;(data?.campaigns||[]).forEach(c=>{
      if(!map.has(c.family)){
        map.set(c.family,{
          attack_id:c.family, name:c.family_name, lifecycle_stage:c.stage,
          variants:ti?.variants||[], detection_signals:ti?.signals||[],
          simulation_type:ti?.simulation_type, surface:ti?.surface,
        })
      }
    })
    return [...map.values()].sort((a,b)=>(a.attack_id||'').localeCompare(b.attack_id||''))
  },[kbFamilies,data,ti])

  const filteredFamilies=useMemo(()=>{
    const q=familyFilter.trim().toLowerCase()
    if(!q)return allFamilies
    return allFamilies.filter(f=>{
      const blob=`${f.attack_id} ${f.name} ${f.lifecycle_stage} ${f.surface} ${f.simulation_type}`.toLowerCase()
      return blob.includes(q)
    })
  },[allFamilies,familyFilter])

  const loopOptions = useMemo(
    () => loops.filter((r) => r.status === "completed" || r.status === "stopped" || r.status === "failed"),
    [loops]
  )

  return(
    <div style={{padding:embedded?'18px 28px 40px':'22px 28px 40px'}}>
      {err&&<div style={{background:'#fef2f2',border:'1px solid #fecaca',borderRadius:8,padding:12,marginBottom:16,fontSize:12,color:'#dc2626'}}>{err}</div>}

      {/* ── Loop + family selectors ── */}
      <div style={{background:'#fff',border:'1px solid #e5e7eb',borderRadius:14,padding:18,marginBottom:16}}>
        <div style={{fontSize:13,fontWeight:600,marginBottom:14}}>
          Browse loop campaigns <span style={{fontWeight:400,color:'#6b7280'}}>({allFamilies.length} KB families)</span>
        </div>
        <div style={{display:'flex',gap:10,alignItems:'center',marginBottom:10,flexWrap:'wrap'}}>
          <select
            value={id}
            onChange={e=>setId(e.target.value)}
            style={{padding:'10px 14px',borderRadius:8,border:'1px solid #e5e7eb',background:'#f9fafb',fontSize:13,minWidth:280,flex:'1 1 280px'}}
          >
            {loopOptions.length===0 && <option value="">No loop runs yet</option>}
            {loopOptions.map(r=>(
              <option key={r.id} value={r.id}>
                {r.id.slice(0,8)} · {r.status} · {r.families_count} fam · lift {r.score_lift!=null?r.score_lift.toFixed(3):'—'}
                {r.val_pr_auc!=null?` · PR ${r.val_pr_auc.toFixed(3)}`:''}
              </option>
            ))}
          </select>
          <input
            value={familyFilter}
            onChange={e=>setFamilyFilter(e.target.value)}
            placeholder="Filter families…"
            style={{padding:'10px 14px',borderRadius:8,border:'1px solid #e5e7eb',background:'#fff',fontSize:13,flex:'0 0 180px'}}
          />
          <select
            value={selectedFamily}
            onChange={e=>{setSelectedFamily(e.target.value);setTab('hyp')}}
            style={{padding:'10px 14px',borderRadius:8,border:'1px solid #e5e7eb',background:'#f9fafb',fontSize:13,flex:1,minWidth:220}}
          >
            <option value="">Select attack family…</option>
            {filteredFamilies.map(f=>{
              const fid=f.attack_id||f.id
              const camp=data?.campaigns.find(c=>c.family===fid)
              const mark=camp?.executed?'●':camp?'○':'·'
              return(
                <option key={fid} value={fid}>
                  {mark} {fid} — {f.name||''}
                  {f.lifecycle_stage?` · ${f.lifecycle_stage}`:''}
                  {Array.isArray(f.variants)?` · ${f.variants.length} var`:''}
                </option>
              )
            })}
          </select>
        </div>
        <div style={{fontSize:11,color:'#6b7280',fontFamily:"'JetBrains Mono',monospace"}}>
          {id?`loop ${id.slice(0,8)} · ${data?.loop_status||'…'}`:'pick a loop'} · ● executed in this run
        </div>
      </div>

      {/* ── KPIs ── */}
      <div className="kpis" style={{gridTemplateColumns:'repeat(5,1fr)',marginBottom:16}}>
        <div className="kpi">
          <span className="label">CAMPAIGNS</span>
          <div className="val">{data?.total_families??0}</div>
          <div className="delta">{data?.executed_families??0} executed · {data?.kb_family_count??allFamilies.length} in KB</div>
        </div>
        <div className="kpi">
          <span className="label">EVENTS</span>
          <div className="val">{data?.total_events??0}</div>
          <div className="delta">buffer pay {data?.buffer_payments??0}</div>
        </div>
        <div className="kpi">
          <span className="label">BLOCKED</span>
          <div className="val">{data?.blocked_count??0}</div>
          <div className="delta">{data?.total_events?Math.round((data.blocked_count/data.total_events)*100):0}% block rate</div>
        </div>
        <div className="kpi">
          <span className="label">BYPASSED</span>
          <div className="val">{data?.bypassed_count??0}</div>
          <div className="delta">{data?.total_events?Math.round((data.bypassed_count/data.total_events)*100):0}% bypass</div>
        </div>
        <div className="kpi">
          <span className="label">NOVELTY</span>
          <div className="val">{selected?.novelty!=null?selected.novelty.toFixed(2):'--'}</div>
          <div className="delta">{selected?.executed?'selected campaign':'KB estimate'}</div>
        </div>
      </div>

      {/* ── Campaign list + detail tabs (side-by-side) ── */}
      <div className="grid-left" style={{gridTemplateColumns:'minmax(280px,340px) 1fr'}}>
        <div className="panel">
          <div className="panel-title" style={{marginBottom:12}}>
            Campaigns for loop
            <span className="tag">{data?.campaigns?.length||0} shown · {data?.executed_families||0} ran</span>
          </div>
          {loading?<Empty>Loading loop campaigns…</Empty>:null}
          {!data?.campaigns?.length&&!loading&&<Empty>No campaign data — start a platform loop from Overview.</Empty>}
          <div className="camp-list">
            {(data?.campaigns||[]).map(c=>(
              <div
                key={c.family}
                className={`camp-row ${c.family===selectedFamily?'active':''}`}
                onClick={()=>{setSelectedFamily(c.family);setTab('hyp')}}
              >
                <div className="top">
                  <span className="fam">{c.family_name}</span>
                  <Badge tone={toneFor(c.status)}>{c.status}</Badge>
                </div>
                <div style={{fontSize:11,color:'var(--muted)',marginTop:2,fontFamily:"'JetBrains Mono',monospace"}}>
                  {c.family} · {c.step} · nov {c.novelty.toFixed(2)}
                </div>
                <div className="meta" style={{marginTop:4}}>
                  <span>{c.stage}</span>
                  <span>{c.executed?`${c.event_count} evt · ${c.blocked}B/${c.bypassed}A`:'KB pad (not in this loop)'}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="detail-tabs">
            <button className={`dtab ${tab==='hyp'?'active':''}`} onClick={()=>setTab('hyp')}>Threat Intelligence</button>
            <button className={`dtab ${tab==='plan'?'active':''}`} onClick={()=>setTab('plan')}>Planner</button>
            <button className={`dtab ${tab==='payload'?'active':''}`} onClick={()=>setTab('payload')}>Payloads</button>
            <button className={`dtab ${tab==='mem'?'active':''}`} onClick={()=>setTab('mem')}>Memory</button>
          </div>

          {!selected?<Empty>Select a campaign or KB family.</Empty>:<>
            {tab==='hyp'&&ti&&(
              <>
                <div className="section-title">Threat Intelligence — {selected.family_name}</div>
                <div className="hyp-box" style={{whiteSpace:'pre-wrap',lineHeight:1.55}}>{ti.summary}</div>
                <div className="chips" style={{marginTop:10}}>
                  {selected.families_tags.map(t=><span key={t} className="chip-inner">{t}</span>)}
                </div>

                <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12,marginTop:16}}>
                  <div style={{padding:12,background:'#f9fafb',borderRadius:8,border:'1px solid #e5e7eb'}}>
                    <div style={{fontSize:10,color:'#6b7280',textTransform:'uppercase',marginBottom:6}}>Objective / Actor</div>
                    <div style={{fontSize:12,lineHeight:1.5}}>
                      <div><strong>Objective:</strong> {ti.objective||'—'}</div>
                      <div style={{marginTop:4}}><strong>Attacker:</strong> {ti.attacker||'—'}</div>
                      <div style={{marginTop:4}}><strong>Target:</strong> {ti.target||'—'}</div>
                      <div style={{marginTop:4}}><strong>Surface:</strong> {ti.surface||'—'} · {ti.simulation_type||'—'}</div>
                    </div>
                  </div>
                  <div style={{padding:12,background:'#f9fafb',borderRadius:8,border:'1px solid #e5e7eb'}}>
                    <div style={{fontSize:10,color:'#6b7280',textTransform:'uppercase',marginBottom:6}}>Coverage</div>
                    <div style={{fontSize:12,lineHeight:1.5}}>
                      <div><strong>Variants:</strong> {ti.variants.length}</div>
                      <div style={{marginTop:4}}><strong>Signals:</strong> {ti.signals.length}</div>
                      <div style={{marginTop:4}}><strong>Controls:</strong> {ti.controls_targeted.length}</div>
                      <div style={{marginTop:4}}><strong>Techniques:</strong> {(ti.technique_ids||[]).join(', ')||'—'}</div>
                      <div style={{marginTop:4}}><strong>Confidence:</strong> {ti.evidence_confidence||'—'}</div>
                    </div>
                  </div>
                </div>

                {ti.prerequisites?.length?(
                  <>
                    <div className="section-title" style={{marginTop:16}}>Prerequisites</div>
                    <ol style={{margin:0,paddingLeft:18,fontSize:12,lineHeight:1.55,color:'#374151'}}>
                      {ti.prerequisites.map((p,i)=><li key={i}>{p}</li>)}
                    </ol>
                  </>
                ):null}

                {ti.attack_flow?.length?(
                  <>
                    <div className="section-title" style={{marginTop:16}}>Attack Flow (KB)</div>
                    <div className="steps">
                      {ti.attack_flow.map((s,i)=>(
                        <div key={i} className="step">
                          <div className="num">{i+1}</div>
                          <div className="body"><div className="desc">{s}</div></div>
                        </div>
                      ))}
                    </div>
                  </>
                ):null}

                {ti.variants?.length?(
                  <>
                    <div className="section-title" style={{marginTop:16}}>Variants</div>
                    <div className="chips">{ti.variants.map(v=><span key={v} className="chip-inner">{v}</span>)}</div>
                  </>
                ):null}

                {ti.signals?.length?(
                  <>
                    <div className="section-title" style={{marginTop:16}}>Detection Signals</div>
                    <div style={{display:'flex',flexDirection:'column',gap:6}}>
                      {ti.signals.map((s,i)=>(
                        <div key={i} style={{fontSize:12,padding:'8px 10px',background:'#f9fafb',borderRadius:6,border:'1px solid #e5e7eb'}}>
                          <strong>{s.name||s.signal_id}</strong>
                          {s.detection_method?<span style={{color:'#6b7280'}}> — {s.detection_method}</span>:null}
                        </div>
                      ))}
                    </div>
                  </>
                ):null}

                {ti.controls_targeted?.length?(
                  <>
                    <div className="section-title" style={{marginTop:16}}>Controls Targeted</div>
                    <div className="chips">{ti.controls_targeted.map(c=><span key={c} className="chip-inner">{c}</span>)}</div>
                  </>
                ):null}
              </>
            )}

            {tab==='plan'&&(
              <>
                <div className="section-title">Attack Planner — {selected.plan.length} steps</div>
                <p style={{margin:'0 0 12px',fontSize:12,color:'#6b7280'}}>
                  KB attack flow merged with observed sandbox decisions from this loop.
                </p>
                <div className="steps">
                  {selected.plan.map((s,i)=>(
                    <div key={i} className="step">
                      <div className="num">{i+1}</div>
                      <div className="body">
                        <div className="title">{s.title}</div>
                        <div className="desc">{s.description}</div>
                        {(s.decision||s.ml_score!=null||s.amount!=null)&&(
                          <div style={{marginTop:6,fontSize:11,fontFamily:"'JetBrains Mono',monospace",color:'#6b7280'}}>
                            {s.decision&&<Badge tone={s.decision}>{s.decision}</Badge>}
                            {s.outcome?` · ${s.outcome}`:''}
                            {s.ml_score!=null?` · ml ${Number(s.ml_score).toFixed(3)}`:''}
                            {s.amount!=null?` · ₹${Number(s.amount).toLocaleString()}`:''}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                {!selected.plan.length&&<Empty>No planner steps for this family.</Empty>}
              </>
            )}

            {tab==='payload'&&(
              <>
                <div className="section-title">
                  Payloads — {(selected.payloads?.length||0)||(selected.payload?1:0)}
                </div>
                <p style={{margin:'0 0 12px',fontSize:12,color:'#6b7280'}}>
                  Evidence buffer + campaign events for this family (real sandbox executions when available).
                </p>
                {(selected.payloads?.length?selected.payloads:[selected.payload]).filter(Boolean).map((p,i)=>(
                  <pre key={i} style={{background:'#f9fafb',border:'1px solid #e5e7eb',borderRadius:8,padding:14,fontSize:11,overflow:'auto',marginBottom:10,maxHeight:280}}>
                    {JSON.stringify(p,null,2)}
                  </pre>
                ))}
                {!selected.payloads?.length&&!selected.payload&&<Empty>No payloads yet.</Empty>}
              </>
            )}

            {tab==='mem'&&(
              <>
                <div className="section-title">Memory Used — {selected.memory.length} entries</div>
                <p style={{margin:'0 0 12px',fontSize:12,color:'#6b7280'}}>
                  Campaign tactics for this run (KB signals/controls + observed outcomes).
                  Full closed-loop learnings (control gaps, buffer evidence, Blue harden signals) →{" "}
                  <a href="/labs" style={{color:'#2563eb',fontWeight:600,textDecoration:'none'}}>Labs</a>.
                </p>
                {selected.memory.map((m,i)=>(
                  <div key={i} className="mem-row">
                    <span className="txt">
                      {m.kind&&<span style={{fontSize:10,color:'#9ca3af',marginRight:6,textTransform:'uppercase'}}>{m.kind}</span>}
                      {m.text}
                    </span>
                    <span className="conf">
                      {(m.source||'kb')} · conf {Number(m.confidence||0).toFixed(2)}
                    </span>
                  </div>
                ))}
                {!selected.memory.length&&<Empty>No memory entries for this campaign.</Empty>}
              </>
            )}
          </>}
        </div>
      </div>
    </div>
  )
}
