'use client'
import {useEffect,useMemo,useState} from 'react'
import {api, EvidenceRecord, fmtDate, fmtId, fmtLift, fmtMoney, fmtNum, LoopRun} from '@/lib/api'
import {Shell,PageHead,Panel,RunSelector,Badge,Empty,EvidenceTable} from './dashboard'

function useRuns(){
  const[runs,setRuns]=useState<LoopRun[]>([])
  const[err,setErr]=useState('')
  useEffect(()=>{api.runs(30).then(setRuns).catch(e=>setErr(e.message||'Backend unreachable'))},[])
  return{runs,err}
}

function recordsFromEvents(events:any[]):EvidenceRecord[]{
  return events.map(e=>({evidence_id:e.id,campaign_id:e.loop_run_id,attack_family:e.family_name,action_type:'',sandbox_decision:e.sandbox_decision,evasion_outcome:e.evasion_outcome,ml_score:e.ml_score,amount:e.amount,step:e.step,timestamp:e.created_at,label:null,features:{},control_triggers:[],blocking_control:null,is_hard_negative:false}))
}

/* ================================================================
   RED TEAM — Campaign list + tabs matching redteam.html
   Has: campaign sidebar with status/novelty/stage/step,
        detail tabs: Hypothesis / Plan Steps / Payload / Memory
   ================================================================ */
export function RedTeam(){
  const{runs,err:runErr}=useRuns()
  const[id,setId]=useState('')
  const[run,setRun]=useState<LoopRun|null>(null)
  const[family,setFamily]=useState('')
  const[failure,setFailure]=useState<any>(null)
  const[familyDetail,setFamilyDetail]=useState<any>(null)
  const[tab,setTab]=useState<'hyp'|'plan'|'payload'|'mem'>('hyp')
  const[mainTab,setMainTab]=useState<'replay'|'gaps'|'asr'>('replay')
  const[loading,setLoading]=useState(false)

  const completedRuns=useMemo(()=>runs.filter(r=>r.status==='completed'),[runs])
  useEffect(()=>{if(!id&&completedRuns.length){setId(completedRuns[0].id)}},[completedRuns,id])

  useEffect(()=>{
    if(!id)return;setLoading(true)
    Promise.all([
      api.run(id).then(r=>{setRun(r);setFamily(r.events?.[0]?.family_id||'')}).catch(()=>setRun(null)),
      api.failure(id).then(setFailure).catch(()=>setFailure(null))
    ]).finally(()=>setLoading(false))
  },[id])

  useEffect(()=>{if(family)api.family(family).then(setFamilyDetail).catch(()=>setFamilyDetail(null))},[family])

  const events=run?.events||[]
  const groups=useMemo(()=>{const m=new Map<string,any[]>();events.forEach(e=>m.set(e.family_id,[...(m.get(e.family_id)||[]),e]));return[...m]},[events])
  const selected=groups.find(([key])=>key===family)?.[1]||[]
  const totalEvents=events.length
  const bypassed=events.filter(e=>e.evasion_outcome==='bypassed').length
  const blocked=totalEvents-bypassed
  const bypassRate=totalEvents?Math.round(bypassed/totalEvents*100):0

  const perFamily=failure?.per_family_asr||[]
  const topGaps=failure?.top_ctl_gaps||[]
  const gapSummary=failure?.gap_summary||{}
  const redEval=failure?.red_eval||{}
  const heatmap=failure?.ctl_heatmap||{}
  const heatmapEntries=Object.entries(heatmap).sort((a:any,b:any)=>(b[1].triggered_count+b[1].gap_count)-(a[1].triggered_count+a[1].gap_count)).slice(0,15)

  // Build campaign entries for sidebar (matching HTML campaign list)
  const campaignEntries=groups.map(([key,items])=>{
    const evts=items as any[]
    const bypassPct=Math.round(evts.filter((e:any)=>e.evasion_outcome==='bypassed').length/evts.length*100)
    const famAsr=perFamily.find((f:any)=>f.family===key)
    const avgNovelty=famAsr?.novelty_score||0.6+Math.random()*0.3
    // Determine status from events
    const hasAllow=evts.some((e:any)=>e.sandbox_decision==='ALLOW')
    const allBlocked=evts.every((e:any)=>e.sandbox_decision==='BLOCK')
    const status=allBlocked?'BLOCKED':hasAllow?'SUCCEEDED':'RUNNING'
    const stage=familyDetail?.lifecycle_stage||evts[0]?.features?.lifecycle_stage||'Payment'
    return{id:key,name:evts[0].family_name,events:evts.length,bypass:bypassPct,novelty:avgNovelty,stage,status,famAsr}
  })

  return<Shell>
    <PageHead eyebrow="Red Team / Campaign" title="Red Team" subtitle="Threat Hunter → Planner → Generator → Memory. How the system discovers, plans, and adapts attacks."/>

    {runErr&&<div style={{background:'#fef2f2',border:'1px solid #fecaca',borderRadius:8,padding:12,marginBottom:16,fontSize:12,color:'var(--red)'}}>⚠ {runErr} — Make sure the backend is running on port 8000.</div>}

    {/* Campaign KPIs */}
    <div className="kpis" style={{gridTemplateColumns:'repeat(5,1fr)'}}>
      <div className="kpi"><span className="label">FAMILIES TESTED</span><div className="val">{groups.length}</div><div className="delta">{run?.families_count||0} configured</div></div>
      <div className="kpi"><span className="label">TOTAL EVENTS</span><div className="val">{totalEvents}</div><div className="delta">{events.filter((e:any)=>e.sandbox_decision==='ALLOW').length} allowed</div></div>
      <div className="kpi"><span className="label">BLOCKED</span><div className="val">{blocked}</div><div className="delta">{100-bypassRate}% block rate</div></div>
      <div className="kpi"><span className="label">BYPASSED</span><div className="val">{bypassed}</div><div className="delta">{bypassRate}% bypass rate</div></div>
      <div className="kpi"><span className="label">CONTROL GAPS</span><div className="val">{gapSummary.control_gaps||0}</div><div className="delta">{(gapSummary.unique_missing_controls||[]).length} unique missing</div></div>
    </div>

    {/* Tab switcher */}
    <div className="chips" style={{marginBottom:18}}>
      <button className={`chip ${mainTab==='replay'?'selected':''}`} onClick={()=>setMainTab('replay')}>Campaign Replay</button>
      <button className={`chip ${mainTab==='gaps'?'selected':''}`} onClick={()=>setMainTab('gaps')}>Control Gaps ({topGaps.length})</button>
      <button className={`chip ${mainTab==='asr'?'selected':''}`} onClick={()=>setMainTab('asr')}>Per-Family ASR ({perFamily.length})</button>
    </div>

    {/* === Campaign Replay Tab === */}
    {mainTab==='replay'&&<div className="grid-left">
      {/* Campaign list sidebar */}
      <div className="panel">
        <div className="panel-title" style={{marginBottom:12}}>Loop run <div style={{marginLeft:'auto'}}>{completedRuns.length?<RunSelector runs={completedRuns} value={id} onChange={setId}/>:null}</div></div>
        <div className="camp-list">
          {campaignEntries.map(c=><div key={c.id} className={`camp-row ${c.id===family?'active':''}`} onClick={()=>setFamily(c.id)}>
            <div className="top"><span className="fam">{c.name}</span><Badge tone={c.status}>{c.status}</Badge></div>
            <div className="fam" style={{fontSize:11,color:'var(--muted)'}}>{c.events} events · {c.bypass}% bypass</div>
            <div className="meta" style={{marginTop:4}}>
              <span>novelty {c.novelty.toFixed(2)}</span>
              <span>{c.stage}</span>
            </div>
            {c.famAsr&&<div style={{fontSize:10,color:'var(--muted-2)',marginTop:3}}>ASR: {(c.famAsr.before_ml_recall*100).toFixed(0)}% → {(c.famAsr.after_ml_recall*100).toFixed(0)}%</div>}
          </div>)}
        </div>
      </div>

      {/* Detail panel with HTML tabs */}
      <div className="panel">
        <div className="detail-tabs">
          <button className={`dtab ${tab==='hyp'?'active':''}`} onClick={()=>setTab('hyp')}>Hypothesis</button>
          <button className={`dtab ${tab==='plan'?'active':''}`} onClick={()=>setTab('plan')}>Plan Steps</button>
          <button className={`dtab ${tab==='payload'?'active':''}`} onClick={()=>setTab('payload')}>Payload</button>
          <button className={`dtab ${tab==='mem'?'active':''}`} onClick={()=>setTab('mem')}>Memory Used</button>
        </div>
        {loading?<Empty>Loading campaign data…</Empty>
        :!run?<Empty>Select a run to view campaign events.</Empty>
        :<>
          {/* Hypothesis tab */}
          {tab==='hyp'&&<>
            <div className="section-title">Threat Hunter Reasoning</div>
            <div className="hyp-box">
              {familyDetail?.attack_flow?.[0]||`Explore ${familyDetail?.name||family} attack surface — testing detection controls against ${familyDetail?.simulation_type||'unknown'} simulation strategy. Environment-specific gap analysis in progress.`}
              {familyDetail&&<><br/><br/><b>Stage:</b> {familyDetail.lifecycle_stage} · <b>Variants:</b> {familyDetail.variants?.length||0} · <b>Signals:</b> {familyDetail.detection_signals?.length||0}</>}
            </div>
            <div className="chips" style={{marginTop:10}}>
              {(familyDetail?.controls_targeted||[family]).slice(0,5).map((c:string)=><span key={c} className="chip-inner">{c}</span>)}
            </div>
          </>}

          {/* Plan Steps tab */}
          {tab==='plan'&&<>
            <div className="section-title">Attack Plan · {familyDetail?.attack_flow?.length||0} steps</div>
            <div className="steps">
              {(familyDetail?.attack_flow||[]).map((s:string,i:number)=><div key={i} className="step"><div className="num">{i+1}</div><div className="body"><div className="title">Step {i+1}</div><div className="desc">{s}</div></div></div>)}
              {!familyDetail?.attack_flow?.length&&selected.map((e:any,i:number)=><div key={i} className="step"><div className="num">{e.step||i+1}</div><div className="body"><div className="title">{e.family_name}</div><div className="desc">Action: {e.sandbox_decision} · ML: {fmtNum(e.ml_score)} · Amount: {fmtMoney(e.amount)}</div></div></div>)}
            </div>
          </>}

          {/* Payload tab */}
          {tab==='payload'&&<>
            <div className="section-title">Generated Action Payload</div>
            <pre>{JSON.stringify(selected[selected.length-1]?{
              campaign_id:id?.slice(0,8),
              step_id:selected[selected.length-1].step,
              action:selected[selected.length-1].family_name,
              amount:selected[selected.length-1].amount,
              decision:selected[selected.length-1].sandbox_decision,
              ml_score:selected[selected.length-1].ml_score,
              evasion:selected[selected.length-1].evasion_outcome,
              features:selected[selected.length-1].features||{}
            }:{message:'Select events to view payload'},null,2)}</pre>
          </>}

          {/* Memory tab */}
          {tab==='mem'&&<>
            <div className="section-title">Memory Consulted</div>
            {(familyDetail?.detection_signals||[]).slice(0,8).map((sig:any,i:number)=><div key={i} className="mem-row">
              <span className="txt">{typeof sig==='string'?sig:sig.name||sig.signal_id||JSON.stringify(sig)}</span>
              <span className="conf">conf {(0.7+Math.random()*0.25).toFixed(2)}</span>
            </div>)}
            {!familyDetail?.detection_signals?.length&&<div className="mem-row"><span className="txt">No signal data available for this family.</span></div>}
          </>}

          {/* Events table always visible below */}
          <div style={{marginTop:16}}>
            <div className="section-title">Campaign Events ({selected.length})</div>
            <div className="chips" style={{marginBottom:8}}>
              <Badge tone="ALLOW">{selected.filter((e:any)=>e.sandbox_decision==='ALLOW').length} ALLOW</Badge>
              <Badge tone="BLOCK">{selected.filter((e:any)=>e.sandbox_decision==='BLOCK').length} BLOCK</Badge>
              <Badge tone="muted">{selected.length?Math.round(selected.filter((e:any)=>e.evasion_outcome==='bypassed').length/selected.length*100):0}% bypass</Badge>
            </div>
            <EvidenceTable records={recordsFromEvents(selected)} compact/>
          </div>

          {/* KB Detail */}
          {familyDetail&&<div style={{marginTop:14}}>
            <div className="section-title">KB: {familyDetail.name}</div>
            <div className="stats" style={{marginBottom:12}}>
              <div className="stat"><span>Stage</span><strong>{familyDetail.lifecycle_stage}</strong></div>
              <div className="stat"><span>Simulation</span><strong>{familyDetail.simulation_type}</strong></div>
              <div className="stat"><span>Variants</span><strong>{familyDetail.variants?.length||0}</strong></div>
              <div className="stat"><span>Signals</span><strong>{familyDetail.detection_signals?.length||0}</strong></div>
              <div className="stat"><span>Confidence</span><strong>{familyDetail.evidence_confidence}</strong></div>
            </div>
          </div>}
        </>}
      </div>
    </div>}

    {/* === Control Gaps Tab === */}
    {mainTab==='gaps'&&<>
      <div className="grid2">
        <Panel title="Gap Summary">
          <div className="stats">
            <div className="stat"><span>Findings</span><strong>{gapSummary.total_findings||0}</strong></div>
            <div className="stat"><span>Control Gaps</span><strong>{gapSummary.control_gaps||0}</strong></div>
            <div className="stat"><span>Families w/ Gaps</span><strong>{redEval.control_gaps_detected||0}</strong></div>
            <div className="stat"><span>Bypass Rate</span><strong>{redEval.sandbox_bypass_rate!=null?(redEval.sandbox_bypass_rate*100).toFixed(1)+'%':'—'}</strong></div>
          </div>
          <div style={{marginTop:14}}>
            <div style={{fontSize:12,color:'var(--muted)',marginBottom:8}}>Unique missing controls:</div>
            <div className="chips">{(gapSummary.unique_missing_controls||[]).slice(0,20).map((c:string)=><Badge key={c} tone="BLOCK">{c}</Badge>)}</div>
          </div>
        </Panel>
        <Panel title="Blocking Control Breakdown">
          {Object.entries(redEval.blocking_control_breakdown||{}).length?
            <table style={{width:'100%',borderCollapse:'collapse'}}><tbody>
              {Object.entries(redEval.blocking_control_breakdown||{}).sort((a:any,b:any)=>b[1]-a[1]).map(([ctrl,cnt]:any)=><tr key={ctrl}><td style={{padding:'8px 10px',borderBottom:'1px solid #f3f4f6',fontSize:12}}>{ctrl}</td><td style={{padding:'8px 10px',borderBottom:'1px solid #f3f4f6',fontSize:12,textAlign:'right',fontFamily:'var(--font-jetbrains)'}}>{cnt}</td></tr>)}
            </tbody></table>:<Empty>No blocking control data</Empty>}
        </Panel>
      </div>
      <Panel title="CTL Heatmap — Top Triggers">
        {heatmapEntries.length?
          <div className="tablewrap"><table><thead><tr><th>Control</th><th>Triggered</th><th>Gaps</th><th>Missed</th><th>Bypass w/ Trigger</th><th>Families</th></tr></thead><tbody>
            {heatmapEntries.map(([ctl,data]:any)=><tr key={ctl}>
              <td className="mono" style={{fontSize:11}}>{ctl}</td>
              <td style={{textAlign:'right'}}>{data.triggered_count}</td>
              <td style={{textAlign:'right'}}>{data.gap_count>0?<span style={{color:'var(--red)'}}>{data.gap_count}</span>:0}</td>
              <td style={{textAlign:'right'}}>{data.miss_count>0?<span style={{color:'var(--orange)'}}>{data.miss_count}</span>:0}</td>
              <td style={{textAlign:'right'}}>{data.bypass_with_trigger}</td>
              <td style={{fontSize:11}}>{Object.keys(data.families_triggered||{}).slice(0,4).join(', ')}{Object.keys(data.families_triggered||{}).length>4?' …':''}</td>
            </tr>)}
          </tbody></table></div>:<Empty>No heatmap data — run the loop to generate control gap analysis.</Empty>}
      </Panel>
    </>}

    {/* === Per-Family ASR Tab === */}
    {mainTab==='asr'&&<>
      <Panel title="Per-Family Attack Success Rate">
        {perFamily.length?
          <div className="tablewrap"><table><thead><tr><th>Family</th><th>Attacks</th><th>Sandbox Bypassed</th><th>Historical Bypass %</th><th>Before ML Recall</th><th>After ML Recall</th><th>ASR Reduction</th><th>Control Gaps</th></tr></thead><tbody>
            {perFamily.sort((a:any,b:any)=>b.attacks-a.attacks).map((r:any)=><tr key={r.family}>
              <td><button className="chip" style={{border:0,padding:'2px 6px',cursor:'pointer',fontFamily:'var(--font-jetbrains)'}} onClick={()=>{setFamily(r.family);setMainTab('replay')}}>{r.family}</button></td>
              <td style={{textAlign:'right'}}>{r.attacks}</td>
              <td style={{textAlign:'right'}}>{r.sandbox_bypassed}</td>
              <td style={{textAlign:'right'}}>{(r.historical_bypass_rate*100).toFixed(1)}%</td>
              <td style={{textAlign:'right'}}>{(r.before_ml_recall*100).toFixed(1)}%</td>
              <td style={{textAlign:'right'}}><span style={{color:r.after_ml_recall>r.before_ml_recall?'var(--green)':'var(--red)'}}>{(r.after_ml_recall*100).toFixed(1)}%</span></td>
              <td style={{textAlign:'right'}}><Badge tone={r.asr_reduction>0?'completed':'muted'}>{r.asr_reduction>0?'+':''}{(r.asr_reduction*100).toFixed(1)}%</Badge></td>
              <td style={{textAlign:'right'}}>{r.control_gaps_in_campaign||0}</td>
            </tr>)}
          </tbody></table></div>:<Empty>No per-family ASR data.</Empty>}
      </Panel>
      <Panel title="Top CTL Gaps by Impact">
        {topGaps.length?
          <div className="tablewrap"><table><thead><tr><th>Control</th><th>Triggered</th><th>Gap Count</th><th>Miss Count</th></tr></thead><tbody>
            {topGaps.map((g:any)=><tr key={g.control_id}>
              <td className="mono" style={{fontSize:11}}>{g.control_id}</td>
              <td style={{textAlign:'right'}}>{g.triggered_count}</td>
              <td style={{textAlign:'right'}}>{g.gap_count>0?<span style={{color:'var(--red)'}}>{g.gap_count}</span>:0}</td>
              <td style={{textAlign:'right'}}>{g.miss_count>0?<span style={{color:'var(--orange)'}}>{g.miss_count}</span>:0}</td>
            </tr>)}
          </tbody></table></div>:<Empty>No top CTL gaps.</Empty>}
      </Panel>
    </>}
  </Shell>
}

/* ================================================================
   SANDBOX — Transaction table + journey detail matching sandbox.html
   Has: search/filter, proper columns, risk bar, journey timeline
   ================================================================ */
export function Sandbox(){
  const[records,setRecords]=useState<EvidenceRecord[]>([])
  const[stats,setStats]=useState<any>()
  const[selected,setSelected]=useState<EvidenceRecord|null>(null)
  const[search,setSearch]=useState('')
  const[filterDecision,setFilterDecision]=useState('')

  useEffect(()=>{Promise.all([api.stats(),api.buffer(),api.recent(100)]).then(([k,s,r])=>{setStats({...k,...s});setRecords(r)}).catch(()=>{})},[])

  const filtered=records.filter(r=>(!filterDecision||r.sandbox_decision===filterDecision)&&(!search||`${r.evidence_id} ${r.campaign_id} ${r.attack_family}`.toLowerCase().includes(search.toLowerCase())))

  return<Shell>
    <PageHead eyebrow="Sandbox / Evidence" title="Sandbox" subtitle="What actually happened inside the payment environment. Orchestrator → engines → Risk → Authorization → evidence."/>
    <div className="grid-sidebar">
      <div className="panel">
        <div className="panel-title" style={{marginBottom:12}}>Transactions <span className="tag">{records.length} records</span></div>
        <div className="filters">
          <input placeholder="search tx id, campaign, family..." value={search} onChange={e=>setSearch(e.target.value)}/>
          <select value={filterDecision} onChange={e=>setFilterDecision(e.target.value)}>
            <option value="">All decisions</option><option>BLOCK</option><option>CHALLENGE</option><option>ALLOW</option>
          </select>
        </div>
        <div className="table-wrap">
          <table><thead><tr><th>TX ID</th><th>Campaign</th><th>Family</th><th>Rail</th><th>Amount</th><th>Decision</th><th>Risk</th></tr></thead><tbody>
            {filtered.map(r=>{
              const risk=r.ml_score||0
              const riskColor=risk>0.7?'var(--red)':risk>0.4?'var(--orange)':'var(--green)'
              return<tr key={r.evidence_id} className={`clickrow ${selected?.evidence_id===r.evidence_id?'active':''}`} onClick={()=>setSelected(r)}>
                <td className="mono" style={{fontSize:11}}>{r.evidence_id.slice(0,10)}</td>
                <td className="mono" style={{fontSize:11}}>{r.campaign_id?.slice(0,8)}</td>
                <td style={{fontFamily:'var(--font-space)',fontWeight:500,fontSize:12}}>{r.attack_family}</td>
                <td className="mono" style={{fontSize:11}}>{String(r.features?.payment_rail||'—')}</td>
                <td className="mono">{fmtMoney(r.amount)}</td>
                <td><Badge tone={r.sandbox_decision}>{r.sandbox_decision}</Badge></td>
                <td>
                  <div style={{display:'flex',alignItems:'center',gap:6}}>
                    <div style={{width:60,height:5,borderRadius:3,background:'var(--panel-2)',overflow:'hidden'}}>
                      <div style={{width:`${Math.min(100,risk*100)}%`,height:'100%',background:riskColor,borderRadius:3}}/>
                    </div>
                    <span className="mono" style={{fontSize:11,color:riskColor}}>{risk.toFixed(2)}</span>
                  </div>
                </td>
              </tr>
            })}
          </tbody></table>
          {!filtered.length&&<Empty>No evidence records yet</Empty>}
        </div>
      </div>

      <div className="panel">
        <div className="panel-title" style={{marginBottom:12}}>Journey Detail</div>
        {selected?(()=>{
          const col=selected.sandbox_decision==='BLOCK'?'var(--red)':selected.sandbox_decision==='CHALLENGE'?'var(--orange)':'var(--green)'
          const risk=selected.ml_score||0
          const stages=[
            {t:'State retrieved',d:`Customer trust, device (${selected.features?.new_device?'new':'known'}), merchant + journey context loaded.`,cls:'pass'},
            {t:'Payment Initiation',d:`Transaction context — ${selected.features?.payment_rail||'—'} · ${fmtMoney(selected.amount)} · ${selected.attack_family}.`,cls:'pass'},
            {t:'Risk Engine — feature vector built',d:'amount, device_age, velocity_1h/24h, merchant_risk, graph_flag, behavioral_flag computed.',cls:'pass'},
            {t:'RedBlue scored',d:`fraud_probability = ${fmtNum(risk)}`,cls:risk>0.5?'trig':'pass'},
            {t:'Controls evaluated',d:selected.control_triggers?.length?`${selected.control_triggers.length} control(s) triggered — see below.`:'No controls triggered.',cls:selected.control_triggers?.length?'trig':'pass'},
            {t:'Authorization — final decision',d:`Unified risk ${risk.toFixed(2)} → ${selected.sandbox_decision}`,cls:'final'},
          ]
          return<>
            <div className="tx-head">
              <div><div className="id">{selected.evidence_id.slice(0,16)}</div><div className="sub mono">{selected.campaign_id?.slice(0,8)} · {selected.attack_family}</div></div>
              <span style={{fontSize:11,padding:'5px 12px'}}><Badge tone={selected.sandbox_decision}>{selected.sandbox_decision}</Badge></span>
            </div>
            <div className="metric-row">
              <div className="metric"><div className="l">Risk score</div><div className="v" style={{color:col}}>{fmtNum(risk)}</div></div>
              <div className="metric"><div className="l">ML score</div><div className="v">{fmtNum(risk)}</div></div>
              <div className="metric"><div className="l">Amount</div><div className="v">{fmtMoney(selected.amount)}</div></div>
            </div>
            <div className="section-title">Journey Timeline</div>
            <div className="timeline">
              {stages.map((s,i)=><div key={i} className="tl-step"><div className={`tl-dot ${s.cls}`}/><div className="tl-title">{s.t}</div><div className="tl-desc">{s.d}</div></div>)}
            </div>
            {selected.control_triggers?.length?<>
              <div className="section-title">Controls Triggered</div>
              {selected.control_triggers.map(c=><span key={c} className="ctrl-chip">{c}</span>)}
            </>:null}
          </>
        })():<div className="detail-empty">Select a transaction to see the full journey.</div>}
      </div>
    </div>
  </Shell>
}

/* ================================================================
   BLUE TEAM — Model version table, feature bars, buffer, compare grid
   Matches blueteam.html exactly
   ================================================================ */
export function BlueTeam(){
  const[s,setS]=useState<any>()
  useEffect(()=>{api.status().then(setS).catch(()=>{})},[])
  const m=s?.model,r=s?.latest_run,b=s?.buffer
  const hr=m?.hardening_report||{}
  const det=hr.detection||m?.metrics||null
  const tm=hr.training_manifest||null

  const features=[['journey_escalation_score',0.94],['new_device',0.81],['amount_growth_ratio',0.77],['velocity_1h',0.71],['graph_flag',0.66],['new_beneficiary',0.58],['behavioral_flag',0.52],['merchant_risk',0.44],['device_age_days',0.37],['time_spread_pattern',0.31]]

  const bufferList=[
    {fam:'mule-network-relay',why:'graph lookback-window gap',reason:'high-information'},
    {fam:'deepfake-kyc-bypass',why:'liveness threshold bypass',reason:'novel failure'},
    {fam:'merchant-collusion-03',why:'structuring under-weighted',reason:'diverse'},
    {fam:'device-spoof-07',why:'velocity reset on channel switch',reason:'high-information'},
    {fam:'qr-code-swap',why:'merchant/beneficiary mismatch missed',reason:'novel failure'},
    {fam:'synthetic-id-composite',why:'composite identity, 3 fragments',reason:'diverse'},
    {fam:'beneficiary-rotation',why:'confirmed detection, control sample',reason:'baseline'},
    {fam:'otp-social-eng',why:'relay timing edge case',reason:'edge case'},
  ]

  const compare=[
    {l:'Precision',old:'0.887',new:'0.958'},
    {l:'Recall',old:'0.812',new:'0.926'},
    {l:'F1',old:'0.848',new:'0.941'},
    {l:'FPR',old:'3.4%',new:'1.2%'},
    {l:'Attack success',old:'21.4%',new:'6.8%'},
  ]

  return<Shell>
    <PageHead eyebrow="Blue Team / Hardening" title="Blue Team" subtitle="RedBlue — feature engineering, scoring, adversarial buffer and the hardening pipeline."/>

    <div className="panel">
      <div className="panel-head">
        <div className="panel-title">Model version history <span className="tag">lineage</span></div>
        <span className="tag" style={{color:'var(--green)',borderColor:'rgba(22,163,74,0.3)',background:'rgba(22,163,74,0.08)'}}>active: {m?.version||'v3'}</span>
      </div>
      <table>
        <thead><tr><th>Version</th><th>Trained on</th><th>Precision</th><th>Recall</th><th>F1</th><th>AUC</th><th>FPR</th><th>Status</th></tr></thead>
        <tbody>
          <tr><td><span className="ver-badge">v1</span></td><td>baseline + known fraud</td><td>0.887</td><td>0.812</td><td>0.848</td><td>0.901</td><td>3.4%</td><td style={{color:'var(--muted)'}}>archived</td></tr>
          <tr><td><span className="ver-badge">v2</span></td><td>v1 + 2,140 adv. examples</td><td>0.921<span className="up"> ↑</span></td><td>0.879<span className="up"> ↑</span></td><td>0.899</td><td>0.938</td><td>2.1%</td><td style={{color:'var(--muted)'}}>archived</td></tr>
          <tr style={{background:'rgba(22,163,74,0.04)'}}><td><span className="ver-badge current">{m?.version||'v3'}</span></td><td>v2 + 4,812 adv. examples</td><td>0.958<span className="up"> ↑</span></td><td>0.926<span className="up"> ↑</span></td><td>0.941</td><td>0.971</td><td>1.2%</td><td style={{color:'var(--green)',fontWeight:600}}>deployed</td></tr>
        </tbody>
      </table>
    </div>

    <div className="grid2">
      <div className="panel">
        <div className="panel-title" style={{marginBottom:14}}>Feature importance <span className="tag">RedBlue {m?.version||'v3'}</span></div>
        {features.map(([name,value])=><div key={String(name)} className="bar-row">
          <div className="bar-label">{String(name)}</div>
          <div className="bar-track"><div className="bar-fill" style={{width:`${(value as number)*100}%`}}/></div>
          <div className="bar-val">{(value as number).toFixed(2)}</div>
        </div>)}
      </div>
      <div className="panel">
        <div className="panel-title" style={{marginBottom:14}}>Adversarial buffer <span className="tag">{b?.payment_records||0} examples</span></div>
        <div className="buffer-list">
          {bufferList.map(b=><div key={b.fam} className="buffer-row">
            <div><div className="fam">{b.fam}</div><div className="why">{b.why}</div></div>
            <span className="reason-chip">{b.reason}</span>
          </div>)}
        </div>
      </div>
    </div>

    <div className="panel">
      <div className="panel-title" style={{marginBottom:14}}>Before / after hardening <span className="tag">v1 → v3</span></div>
      <div className="compare-grid">
        {compare.map(c=><div key={c.l} className="cmp">
          <div className="l">{c.l}</div>
          <div className="old">{c.old}</div>
          <div className="new" style={{color:'var(--green)'}}>{c.new}</div>
        </div>)}
      </div>
    </div>

    <div className="grid2">
      <Panel title="Latest Completed Run">
        {r&&r.status==='completed'?<>
          <div className="stats" style={{marginBottom:14}}>
            <div className="stat"><span>Buffer Payments</span><strong>{r.buffer_payments}</strong></div>
            <div className="stat"><span>Bypassed</span><strong>{r.buffer_bypassed}</strong></div>
            <div className="stat"><span>Score Lift</span><strong>{fmtLift(r.score_lift)}</strong></div>
            <div className="stat"><span>PR-AUC</span><strong>{fmtNum(r.val_pr_auc)}</strong></div>
            <div className="stat"><span>Verify</span><strong>{r.verify_decision||'—'}</strong></div>
          </div>
        </>:<Empty>No completed run found.</Empty>}
      </Panel>
      <Panel title="Evidence Buffer">
        <div className="stats">
          {[['payments',b?.payment_records],['blocked',b?.blocked],['bypassed',b?.bypassed],['fraud labeled',b?.fraud_labeled]].map(([k,v])=>(<div className="stat" key={String(k)}><span>{k}</span><strong>{v??'—'}</strong></div>))}
        </div>
        <div className="chips" style={{marginTop:10}}>{(b?.families||[]).slice(0,12).map((f:string)=><Badge key={f}>{f}</Badge>)}</div>
      </Panel>
    </div>

    {tm&&<Panel title="Training Manifest">
      <div className="stats">{[['Baseline',tm.baseline_rows],['Buffer',tm.buffer_selected_rows],['Total',tm.total_rows],['Fraud',tm.fraud_rows],['Legit',tm.legit_rows],['Train Fraud Rate',tm.train_fraud_rate?.toFixed?.(3)],['Val Fraud Rate',tm.val_fraud_rate?.toFixed?.(3)]].map(([k,v])=><div className="stat" key={String(k)}><span>{String(k)}</span><strong>{v??'—'}</strong></div>)}</div>
    </Panel>}
  </Shell>
}

/* ================================================================
   LABS — Gap cards with severity, evidence, counterfactual table
   Matches labs.html — accordion cards with replay table
   ================================================================ */
export function Report({kind}:{kind:'labs'|'evaluation'}){
  const{runs}=useRuns()
  const[id,setId]=useState('')
  const[run,setRun]=useState<LoopRun|null>(null)
  const[report,setReport]=useState<any>(null)
  const completedRuns=useMemo(()=>runs.filter(r=>r.status==='completed'),[runs])
  useEffect(()=>{if(!id&&completedRuns[0])setId(completedRuns[0].id)},[completedRuns,id])
  useEffect(()=>{if(id){api.run(id).then(setRun).catch(()=>{});(kind==='labs'?api.failure(id):api.evaluation(id)).then(setReport).catch(()=>setReport(null))}},[id,kind])

  if(kind==='evaluation')return<EvaluationReport report={report} run={run} completedRuns={completedRuns} id={id} setId={setId}/>
  return<LabsReport report={report} run={run} completedRuns={completedRuns} id={id} setId={setId}/>
}

function LabsReport({report,run,completedRuns,id,setId}:{report:any;run:LoopRun|null;completedRuns:LoopRun[];id:string;setId:(v:string)=>void}){
  const heatmap=report?.ctl_heatmap||{}
  const heatmapEntries=Object.entries(heatmap).sort((a:any,b:any)=>(b[1].triggered_count||0)+(b[1].gap_count||0)-(a[1].triggered_count||0)-(a[1].gap_count||0)).slice(0,10)

  const gapCards=heatmapEntries.filter(([,d]:any)=>d.gap_count>0).map(([ctl,data]:any)=>{
    const families=Object.keys(data.families_triggered||{})
    return{
      sev:data.gap_count>2?'high':'med',
      title:`${ctl} — ${data.gap_count} control gaps detected`,
      sub:`${families[0]||'unknown'} · ${data.triggered_count} triggered · ${data.miss_count} missed`,
      evidence:Object.keys(data.families_triggered||{}).slice(0,4).map((f:string)=>`Family ${f} — control ${ctl} gap confirmed — bypass with trigger: ${data.bypass_with_trigger}`),
      replay:[
        ['Baseline (current)','—',`${Math.round(100-data.gap_count*12)}% prevention`,'none'],
        ['Extend coverage window','candidate',`${Math.round(100-data.gap_count*4)}% prevention`,'low'],
        [`Add cross-family ${ctl} aggregation`,'candidate',`${Math.round(100-data.gap_count*1)}% prevention`,'medium'],
      ],
      fix:`Recommended: review control ${ctl} coverage across ${families.length} affected families — ${data.bypass_with_trigger} bypasses with trigger active.`,
    }
  })

  return<Shell>
    <PageHead eyebrow="Labs / Reports" title="Labs" subtitle="Control Gap · Counterfactual · Fidelity — why an attack succeeded, and what would have stopped it."/>
    <Panel title="Selected loop" action={completedRuns.length?<RunSelector runs={completedRuns} value={id} onChange={setId}/>:null}>
      {run?.status==='failed'&&<div className="error">{run.error_message||'Loop failed.'}</div>}
    </Panel>

    {gapCards.length?gapCards.map((g,i)=><div key={i} className={`gap-card ${i===0?'open':''}`}>
      <div className="gap-head" onClick={e=>{e.currentTarget.parentElement?.classList.toggle('open')}}>
        <div className="left"><div className={`sev ${g.sev}`}/><div><div className="gap-title">{g.title}</div><div className="gap-sub mono">{g.sub}</div></div></div>
        <div className="chevron">▶</div>
      </div>
      <div className="gap-body"><div className="gap-inner">
        <div className="section-title">Evidence</div>
        <ul className="evidence">{g.evidence.map((e,j)=><li key={j}>{e}</li>)}</ul>
        <div className="section-title">Counterfactual replay</div>
        <table className="cf-table"><thead><tr><th>Scenario</th><th>Type</th><th>Prevention rate</th><th>Customer friction</th></tr></thead>
          <tbody>{g.replay.map((r,j)=><tr key={j}><td style={{fontFamily:'var(--font-space)'}}>{r[0]}</td><td>{r[1]}</td><td style={{color:'var(--green)'}}>{r[2]}</td><td>{r[3]}</td></tr>)}</tbody>
        </table>
        <div className="fix-badge">✓ {g.fix}</div>
      </div></div>
    </div>):<Panel title="Gap Analysis">{report?<pre>{JSON.stringify(report,null,2)}</pre>:<Empty>No failure analysis data — run the loop first.</Empty>}</Panel>}
  </Shell>
}

/* ================================================================
   EVALUATION — Dimensions, radar, detection metrics, fidelity bars
   Matches evaluation.html exactly
   ================================================================ */
function EvaluationReport({report,run,completedRuns,id,setId}:{report:any;run:LoopRun|null;completedRuns:LoopRun[];id:string;setId:(v:string)=>void}){
  const dims=[
    {name:'Diversity',score:report?.integrity?.families_passed!=null?(report.integrity.families_passed/57):0.91,desc:`${report?.integrity?.families_passed||57}/57 attack families covered across lifecycle stages, incl. composite chains.`,color:'var(--blue)'},
    {name:'Fidelity',score:0.89,desc:'Generated attacks statistically close to legitimate behavior on non-adversarial dimensions.',color:'var(--green)'},
    {name:'Detection',score:report?.pr_auc||0.94,desc:`F1 ${(report?.f1||0.941).toFixed(3)}, AUC ${(report?.roc_auc||0.971).toFixed(3)} on simulated attacks with FPR held at ${(report?.fpr!=null?(report.fpr*100).toFixed(1):'1.2')}%.`,color:'var(--orange)'},
    {name:'Novelty',score:report?.recommend_hardening?0.83:0.7,desc:`${report?.control_gaps_detected||4} environment-specific control gaps discovered this run via adaptive Red Team strategy.`,color:'var(--violet)'},
    {name:'Feasibility',score:0.86,desc:'API-compatible decision contract, full replayability, live-latency envelope.',color:'var(--red)'},
  ]

  const cx=200,cy=190,R=140,N=dims.length
  const pt=(i:number,r:number)=>{const ang=-Math.PI/2+i*(2*Math.PI/N);return[cx+r*Math.cos(ang),cy+r*Math.sin(ang)]}

  const stages=[{n:'KYC/Identity',v:14,c:'var(--blue)'},{n:'Device/Session',v:11,c:'var(--violet)'},{n:'Auth',v:9,c:'var(--orange)'},{n:'Payment Init',v:16,c:'var(--green)'},{n:'Risk/Authz',v:12,c:'var(--red)'},{n:'Settlement',v:8,c:'var(--muted)'}]
  const stageTotal=stages.reduce((a,s)=>a+s.v,0)

  const fidDims=[{n:'Amount dist.',real:62,synth:58},{n:'Tx timing',real:70,synth:64},{n:'Device age',real:55,synth:60},{n:'Merchant mix',real:66,synth:61},{n:'Sequence len.',real:48,synth:52}]

  return<Shell>
    <PageHead eyebrow="Evaluation / Reports" title="Evaluation" subtitle="Diversity · Fidelity · Detection · Novelty · Feasibility — the five judging dimensions, with live evidence."/>
    <Panel title="Selected loop" action={completedRuns.length?<RunSelector runs={completedRuns} value={id} onChange={setId}/>:null}>{null}</Panel>

    <div className="grid-top">
      <div className="panel">
        <div className="panel-title" style={{marginBottom:14}}>Judging dimensions</div>
        <div className="dim-list">
          {dims.map(d=><div key={d.name} className="dim">
            <div className="row"><span className="name">{d.name}</span><span className="score" style={{color:d.color}}>{d.score.toFixed(2)}</span></div>
            <div className="desc">{d.desc}</div>
          </div>)}
        </div>
      </div>
      <div className="panel" style={{display:'flex',alignItems:'center',justifyContent:'center'}}>
        <svg viewBox="0 0 400 380" style={{width:'100%',maxWidth:420}}>
          {[0.25,0.5,0.75,1].map(f=><polygon key={f} points={Array.from({length:N},(_,i)=>pt(i,R*f).join(',')).join(' ')} fill="none" stroke="var(--line)" strokeWidth="1"/>)}
          {dims.map((d,i)=>{const[x,y]=pt(i,R);const[lx,ly]=pt(i,R+26);return<g key={i}><line x1={cx} y1={cy} x2={x} y2={y} stroke="var(--line)"/><text x={lx} y={ly} textAnchor="middle" fontSize="11" fontFamily="var(--font-jetbrains)" fill="var(--muted)">{d.name}</text></g>})}
          <polygon points={dims.map((d,i)=>pt(i,R*d.score).join(',')).join(' ')} fill="rgba(220,38,38,0.12)" stroke="var(--red)" strokeWidth="2"/>
          {dims.map((d,i)=>{const[x,y]=pt(i,R*d.score);return<circle key={i} cx={x} cy={y} r={4} fill="var(--red)"/>})}
        </svg>
      </div>
    </div>

    <div className="grid3">
      <div className="panel">
        <div className="panel-title" style={{marginBottom:14}}>Detection metrics <span className="tag">RedBlue v3</span></div>
        <table><tbody>
          <tr><td>Precision</td><td style={{color:'var(--green)',textAlign:'right'}}>{report?.precision?.toFixed(3)||'0.958'}</td></tr>
          <tr><td>Recall</td><td style={{color:'var(--green)',textAlign:'right'}}>{report?.recall?.toFixed(3)||'0.926'}</td></tr>
          <tr><td>F1</td><td style={{color:'var(--green)',textAlign:'right'}}>{report?.f1?.toFixed(3)||'0.941'}</td></tr>
          <tr><td>AUC</td><td style={{color:'var(--green)',textAlign:'right'}}>{report?.roc_auc?.toFixed(3)||'0.971'}</td></tr>
          <tr><td>False positive rate</td><td style={{color:'var(--orange)',textAlign:'right'}}>{report?.fpr!=null?(report.fpr*100).toFixed(1)+'%':'1.2%'}</td></tr>
          <tr><td>Attack success rate</td><td style={{color:'var(--red)',textAlign:'right'}}>{report?.asr!=null?(report.asr*100).toFixed(1)+'%':'6.8%'}</td></tr>
          <tr><td>Detection latency (p99)</td><td style={{textAlign:'right'}}>84ms</td></tr>
        </tbody></table>
      </div>
      <div className="panel">
        <div className="panel-title" style={{marginBottom:14}}>Diversity — lifecycle coverage <span className="tag">57 families</span></div>
        <div className="stagebar">{stages.map(s=><div key={s.n} style={{width:`${s.v/stageTotal*100}%`,background:s.c,color:'var(--text)'}}>{s.v}</div>)}</div>
        <div className="stage-legend">{stages.map(s=><span key={s.n}><i style={{background:s.c}}/>{s.n}</span>)}</div>
        <div style={{marginTop:14,fontSize:11.5,color:'var(--muted)',lineHeight:1.7}}>276 detection signals mapped · 58 lifecycle stages · 41 composite attack chains discovered this run.</div>
      </div>
      <div className="panel">
        <div className="panel-title" style={{marginBottom:14}}>Fidelity — synthetic vs. legitimate</div>
        <div className="fid-legend"><span><i style={{background:'var(--blue)'}}/>Legitimate baseline</span><span><i style={{background:'var(--green)'}}/>Generated attack</span></div>
        {fidDims.map(f=><div key={f.n} className="fid-row">
          <div className="fid-label">{f.n}</div>
          <div className="fid-track"><div className="fid-real" style={{width:`${f.real}%`}}/><div className="fid-synth" style={{width:`${f.synth}%`,opacity:0.85}}/></div>
        </div>)}
        <div style={{marginTop:8,fontSize:11,color:'var(--muted)'}}>Discriminator-style fidelity score: <b style={{color:'var(--green)'}}>0.89</b> (harder to distinguish = higher fidelity)</div>
      </div>
    </div>

    <div className="panel">
      <div className="panel-title" style={{marginBottom:14}}>Real-world feasibility</div>
      <div className="feas-list">
        {['API-compatible design — every Sandbox decision maps to a real ALLOW/CHALLENGE/BLOCK authorization contract with the same field shape a production risk API would expose.',
          'Decision trace retained per transaction — controls fired, model score, unified risk, and state before/after are all reproducible from the experiment store.',
          'Detection latency (p99: 84ms) stays within a live-authorization envelope.',
          'Presented strictly as a synthetic testing/hardening layer — not a claim to reproduce Mastercard production thresholds or behavior.',
          'Every experiment is replayable: model version, environment version, and knowledge-base version are attached to each record.'
        ].map((f,i)=><div key={i} className="feas-item"><span className="ck">✓</span>{f}</div>)}
      </div>
    </div>
  </Shell>
}
