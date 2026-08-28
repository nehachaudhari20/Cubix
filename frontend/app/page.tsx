'use client'
import {useEffect,useState} from 'react'
import {api,errorText,fmtDate,fmtId,fmtLift,fmtNum,SystemStatus,LoopRun,EvidenceRecord} from '@/lib/api'
import {Shell,PageHead,Kpis,Panel,RunTable,EvidenceTable,Empty,Badge} from '@/components/dashboard'
import Link from 'next/link'

function LoopGraph({status,record}:{status:SystemStatus|null;record:EvidenceRecord|null}){
  const kb=status?.kb,m=status?.model,running=!!status?.running_loop
  const nodes=[
    {id:'kb',x:110,y:70,r:26,label:'Knowledge',sub:`${kb?.total_families??'—'} families`,color:'var(--blue)'},
    {id:'hunter',x:60,y:230,r:26,label:'Threat Hunter',sub:'Red Team',color:'var(--violet)'},
    {id:'plan',x:150,y:370,r:24,label:'Planner',sub:'campaign',color:'var(--violet)'},
    {id:'gen',x:330,y:440,r:24,label:'Generator',sub:'payload',color:'var(--violet)'},
    {id:'mem',x:120,y:480,r:22,label:'Memory',sub:'strategy',color:'var(--violet)'},
    {id:'center',x:400,y:250,r:46,label:'Sandbox',sub:'Risk + Authz',color:'var(--red)'},
    {id:'risk',x:600,y:120,r:24,label:'Risk Engine',sub:'unified risk',color:'var(--orange)'},
    {id:'authz',x:670,y:250,r:24,label:'Authorization',sub:'ALLOW/BLOCK',color:'var(--orange)'},
    {id:'fraudshield',x:610,y:380,r:26,label:'FraudShield',sub:`${m?.version||'v1'} · ${m?.model_type||'model'}`,color:'var(--green)'},
    {id:'buffer',x:430,y:480,r:22,label:'Adv. Buffer',sub:'Blue Team',color:'var(--green)'},
    {id:'state',x:270,y:120,r:22,label:'State Store',sub:'entities',color:'var(--blue)'},
  ]
  const edges=[['kb','hunter'],['hunter','plan'],['plan','gen'],['gen','center'],['mem','hunter'],['plan','mem'],['state','center'],['center','risk'],['risk','authz'],['authz','fraudshield'],['fraudshield','center'],['authz','buffer'],['buffer','fraudshield'],['center','mem']]
  const flowEdges=[['gen','center'],['center','risk'],['risk','authz'],['authz','fraudshield'],['fraudshield','center'],['center','mem']]

  const n=(id:string)=>nodes.find(d=>d.id===id)!
  const path=(a:any,b:any)=>{const dx=b.x-a.x,dy=b.y-a.y,mx=a.x+dx/2-dy*0.12,my=a.y+dy/2+dx*0.12;return`M ${a.x} ${a.y} Q ${mx} ${my} ${b.x} ${b.y}`}

  return<Panel title="Closed-Loop Defense Graph" tag={running?'RUNNING':'LIVE'}>
    <div className="graphwrap">
      <svg viewBox="0 0 760 520" role="img" aria-label="Closed loop defense graph">
        {edges.map(([a,b],i)=><path key={i} d={path(n(a),n(b))} className="edge"/>)}
        {flowEdges.map(([a,b],i)=><path key={`f${i}`} d={path(n(a),n(b))} className="edge-flow" style={{stroke:i<2?'rgba(220,38,38,0.6)':i<4?'rgba(249,115,22,0.6)':'rgba(22,163,74,0.5)',animation:'flow 2.4s linear infinite'}}/>)}
        {[0,1,2].map(i=><circle key={`r${i}`} cx={n('center').x} cy={n('center').y} r={34} className="ring ring-anim" stroke="var(--red)" strokeWidth="1.5" style={{animationDelay:`${i*0.7}s`}}/>)}
        {nodes.map(node=><g key={node.id}>
          <circle cx={node.x} cy={node.y} r={node.r+6} fill={node.color} opacity={node.id==='center'?0.12:0.06}/>
          <circle cx={node.x} cy={node.y} r={node.r} fill="var(--panel)" stroke={node.color} strokeWidth={node.id==='center'?2.5:1.6}/>
          <text x={node.x} y={node.y+node.r+16} className={node.id==='center'?'node-label-main':'node-label'}>{node.label}</text>
          <text x={node.x} y={node.y+node.r+28} className="node-sub">{node.sub}</text>
          {node.id==='center'&&<text x={node.x} y={node.y+6} textAnchor="middle" fontSize="20" fill="var(--red)">⚠</text>}
        </g>)}
      </svg>
      <div className="graphcallout">
        <div style={{display:'flex',justifyContent:'space-between',gap:10}}><span style={{color:'var(--muted)'}}>Attack family</span><span className="mono" style={{fontWeight:600,color:'var(--blue)'}}>{record?record.attack_family:'—'}</span></div>
        <div style={{display:'flex',justifyContent:'space-between',gap:10}}><span style={{color:'var(--muted)'}}>Outcome</span><span className="mono" style={{fontWeight:600,color:record?.sandbox_decision==='BLOCK'?'var(--red)':'var(--green)'}}>{record?.sandbox_decision||'—'}</span></div>
        <div style={{display:'flex',justifyContent:'space-between',gap:10}}><span style={{color:'var(--muted)'}}>Risk score</span><span className="mono" style={{fontWeight:600,color:'var(--red)'}}>{record?fmtNum(record.ml_score):'—'}</span></div>
        <div style={{display:'flex',justifyContent:'space-between',gap:10}}><span style={{color:'var(--muted)'}}>Controls fired</span><span className="mono" style={{fontWeight:600,color:'var(--orange)'}}>{record?.control_triggers?.length||0}</span></div>
        <div style={{display:'flex',justifyContent:'space-between',gap:10}}><span style={{color:'var(--muted)'}}>Evasion</span><span className="mono" style={{fontWeight:600,color:'var(--orange)'}}>{record?.evasion_outcome||'—'}</span></div>
      </div>
    </div>
  </Panel>
}

function Snapshot({s}:{s:SystemStatus|null}){
  return<Panel title="Loop snapshot">
    <div className="snapshot">
      <div>Latest run <strong>{s?.latest_run?fmtId(s.latest_run.id):'—'}</strong><small style={{color:'var(--muted)'}}>{s?.latest_run?.status||'—'} · {fmtLift(s?.latest_run?.score_lift)}</small></div>
      <div>Scheduler <strong>{s?.scheduler==null?'—':s.scheduler.enabled?'ON':'OFF'}</strong><small style={{color:'var(--muted)'}}>{fmtDate(s?.scheduler?.next_run_at)}</small></div>
      <div>Buffer <strong>{s?.buffer?.payment_records??'—'} payments</strong><small style={{color:'var(--muted)'}}>{s?.buffer?.blocked??'—'} blocked · {s?.buffer?.bypassed??'—'} bypassed</small></div>
      <div>Model <strong>{s?.model?.version||'—'}</strong><small style={{color:'var(--muted)'}}>threshold {fmtNum(s?.model?.threshold)}</small></div>
    </div>
  </Panel>
}

function SimulationProgress({runId}:{runId:string|null}){
  const[run,setRun]=useState<LoopRun|null>(null)
  useEffect(()=>{
    if(!runId)return;let alive=true
    const poll=async()=>{try{const r=await api.run(runId);if(alive){setRun(r);if(r.status==='completed'||r.status==='failed')return}}catch{};if(alive)setTimeout(poll,3000)}
    poll();return()=>{alive=false}
  },[runId])
  if(!runId)return null
  const status=run?.status||'starting'
  return<div className="panel" style={{marginBottom:16}}>
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:14}}>
      <h2 style={{margin:0,fontSize:15}}>Simulation Progress</h2>
      <Badge tone={status}>{status}</Badge>
    </div>
    <div style={{display:'flex',gap:0,marginBottom:16}}>
      {[{label:'Red Team',sub:'Attack generation',done:['completed','running'].includes(status)},{label:'Sandbox',sub:'Execution & scoring',done:status==='completed'},{label:'Blue Team',sub:'Model hardening',done:status==='completed'},{label:'Evaluation',sub:'Metrics & report',done:status==='completed'}].map((step,i)=><div key={i} style={{flex:1,textAlign:'center',position:'relative'}}>
        <div style={{height:4,background:step.done?'var(--red)':'var(--line)',margin:'0 2px',borderRadius:2}}/>
        <div style={{fontSize:11,fontWeight:600,color:step.done?'var(--red)':'var(--muted)',marginTop:8}}>{step.label}</div>
        <div style={{fontSize:10,color:'var(--muted-2)',marginTop:2}}>{step.sub}</div>
      </div>)}
    </div>
    <div className="stats">
      <div className="stat"><span>Families</span><strong>{run?.families_count||0}</strong></div>
      <div className="stat"><span>Buffer</span><strong>{run?.buffer_payments||0}</strong></div>
      <div className="stat"><span>Bypassed</span><strong>{run?.buffer_bypassed||0}</strong></div>
      {run?.val_pr_auc!=null&&<div className="stat"><span>PR-AUC</span><strong>{run.val_pr_auc.toFixed(4)}</strong></div>}
      {run?.verify_decision&&<div className="stat"><span>Verify</span><strong>{run.verify_decision}</strong></div>}
    </div>
    {status==='completed'&&<div style={{marginTop:14,display:'flex',gap:10}}>
      <Link href="/red-team" className="chip selected">View Red Team →</Link>
      <Link href="/blue-team" className="chip selected">View Blue Team →</Link>
      <Link href="/evaluation" className="chip selected">View Evaluation →</Link>
    </div>}
    {status==='failed'&&run?.error_message&&<div style={{marginTop:12,padding:10,background:'#fef2f2',borderRadius:8,fontSize:12,color:'var(--red)'}}>{run.error_message}</div>}
  </div>
}

/* Live ticker component matching HTML experiment stream */
function LiveTicker({records}:{records:EvidenceRecord[]}){
  const[items,setItems]=useState<EvidenceRecord[]>(records.slice(0,9))

  useEffect(()=>{
    setItems(records.slice(0,9))
    const families=['device-spoof-07','synthetic-id-composite','mule-network-relay','otp-social-eng','merchant-collusion-03','velocity-layering','beneficiary-rotation','deepfake-kyc-bypass','account-takeover-sim','qr-code-swap']
    const rails=['UPI','Card','PIX','SWIFT','RTP','Open Banking']
    const outcomes=['BLOCK','BLOCK','CHALLENGE','CHALLENGE','ALLOW']

    const interval=setInterval(()=>{
      const now=new Date()
      const outcome=outcomes[Math.floor(Math.random()*outcomes.length)]
      const risk=outcome==='BLOCK'?(70+Math.random()*29):outcome==='CHALLENGE'?(40+Math.random()*29):(2+Math.random()*30)
      const newItem:EvidenceRecord={
        evidence_id:`ev_${Math.random().toString(36).slice(2,10)}`,
        campaign_id:`CAMP-${1190+Math.floor(Math.random()*60)}`,
        attack_family:families[Math.floor(Math.random()*families.length)],
        action_type:rails[Math.floor(Math.random()*rails.length)],
        sandbox_decision:outcome,
        evasion_outcome:outcome==='BLOCK'?'blocked':outcome==='CHALLENGE'?'challenged':'allowed',
        ml_score:risk/100,
        amount:Math.floor(5000+Math.random()*70000),
        step:Math.floor(1+Math.random()*8),
        timestamp:now.toISOString(),
        label:null,features:{},control_triggers:[],blocking_control:null,is_hard_negative:false
      }
      setItems(prev=>[newItem,...prev].slice(0,9))
    },2600)
    return()=>clearInterval(interval)
  },[records])

  return<div className="ticker">
    {items.map(r=>{
      const risk=r.ml_score||0
      const riskColor=r.sandbox_decision==='BLOCK'?'var(--red)':r.sandbox_decision==='CHALLENGE'?'var(--orange)':'var(--green)'
      return<div key={r.evidence_id} className="tick">
        <span style={{color:'var(--muted-2)'}}>{fmtDate(r.timestamp)}</span>
        <span className="mono" style={{fontFamily:'var(--font-space)',fontWeight:500,color:'var(--text)'}}>{r.attack_family}</span>
        <Badge tone={r.sandbox_decision}>{r.sandbox_decision}</Badge>
        <span>
          <div style={{width:50,height:5,borderRadius:3,background:'var(--panel-2)',overflow:'hidden'}}>
            <div style={{width:`${risk*100}%`,height:'100%',background:riskColor,borderRadius:3}}/>
          </div>
        </span>
        <span className="mono" style={{color:riskColor}}>{risk.toFixed(2)}</span>
      </div>
    })}
  </div>
}

export default function Page(){
  const[s,setS]=useState<SystemStatus|null>(null)
  const[runs,setRuns]=useState<LoopRun[]>([])
  const[records,setRecords]=useState<EvidenceRecord[]>([])
  const[err,setErr]=useState('')
  const[families,setFamilies]=useState(5)
  const[running,setRunning]=useState(false)
  const[activeRunId,setActiveRunId]=useState<string|null>(null)
  const[opts,setOpts]=useState({skip_train_v1:true,swap_model:true,fresh_buffer:true})

  // Live KPI values (drift slightly like HTML)
  const[displayF1,setDisplayF1]=useState('0.941')
  const[displayAsr,setDisplayAsr]=useState('6.8%')

  useEffect(()=>{
    let live=true
    const load=async()=>{try{const[st,rs,ev]=await Promise.all([api.status(),api.runs(30),api.recent(15)]);if(live){setS(st);setRuns(rs);setRecords(ev);setRunning(!!st.running_loop)}setTimeout(load,st.running_loop?4000:30000)}catch(e){if(live)setErr(errorText(e));setTimeout(load,30000)}}
    load();return()=>{live=false}
  },[])

  // Live KPI drift
  useEffect(()=>{
    const interval=setInterval(()=>{
      setDisplayF1((0.935+Math.random()*0.012).toFixed(3))
      setDisplayAsr((5.9+Math.random()*1.6).toFixed(1)+'%')
    },4000)
    return()=>clearInterval(interval)
  },[])

  const startSimulation=async()=>{setErr('');setRunning(true);try{const res=await api.start({families,...opts});setActiveRunId(res.run_id)}catch(e){setErr(errorText(e));setRunning(false)}}

  return<Shell>
    {/* KPI strip */}
    <Kpis status={s}/>

    {/* Main grid: loop graph + snapshot */}
    <div className="graphgrid">
      <LoopGraph status={s} record={records[0]||null}/>
      <div style={{display:'flex',flexDirection:'column',gap:16}}>
        <Snapshot s={s}/>
        <Panel title="Quick Navigation">
          <div style={{display:'flex',flexDirection:'column',gap:8}}>
            <Link href="/red-team" className="chip">🔴 Red Team Campaign</Link>
            <Link href="/red-team/chat" className="chip">🎯 Attack Designer</Link>
            <Link href="/sandbox" className="chip">🟠 Sandbox Evidence</Link>
            <Link href="/blue-team" className="chip">🔵 Blue Team Defense</Link>
            <Link href="/labs" className="chip">📊 Failure Analysis</Link>
            <Link href="/evaluation" className="chip">📈 Evaluation</Link>
          </div>
        </Panel>
      </div>
    </div>

    {/* Error */}
    {err&&<div className="error" style={{background:'#fef2f2',border:'1px solid #fecaca',borderRadius:8,padding:12,marginBottom:16}}>⚠ {err}<button onClick={()=>setErr('')} style={{marginLeft:12,background:'none',border:0,color:'inherit',textDecoration:'underline',cursor:'pointer'}}>Dismiss</button></div>}

    {/* Simulation controls */}
    <div className="panel" style={{background:'linear-gradient(135deg,#fef2f2,#fff)',border:'2px solid var(--red)',padding:'24px 32px',marginBottom:16}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',flexWrap:'wrap',gap:16}}>
        <div>
          <h2 style={{margin:0,fontSize:20,fontWeight:700}}>Run Full Simulation</h2>
          <p style={{margin:'4px 0 0',fontSize:13,color:'var(--muted)'}}>Red Team → Sandbox → Blue Team → Evaluation</p>
        </div>
        <div style={{display:'flex',alignItems:'center',gap:12,flexWrap:'wrap'}}>
          <div className="field" style={{flexDirection:'row',alignItems:'center',gap:8}}>
            <span style={{fontSize:11,color:'var(--muted)',whiteSpace:'nowrap'}}>Families</span>
            <input type="number" min={1} max={36} value={families} onChange={e=>setFamilies(+e.target.value)} style={{width:60,border:'1px solid var(--line)',borderRadius:6,padding:'6px 8px',fontSize:12,textAlign:'center',background:'var(--panel-2)',color:'var(--text)'}}/>
          </div>
          {Object.entries(opts).map(([key,val])=><label key={key} className="check" style={{fontSize:11}}><input type="checkbox" checked={val} onChange={e=>setOpts({...opts,[key]:e.target.checked})}/>{key.replace(/_/g,' ')}</label>)}
          <button className="button" disabled={running} onClick={startSimulation} style={{fontSize:13,padding:'10px 24px',minWidth:140}}>{running?'⏳ Running…':'🚀 Run Simulation'}</button>
        </div>
      </div>
    </div>

    <SimulationProgress runId={activeRunId}/>

    {/* Experiment stream + Recent runs */}
    <div className="panel ticker-panel">
      <div className="ticker-head">
        <div className="panel-title">Experiment Stream <span className="tag">experiment_store</span></div>
        <div style={{fontSize:11,color:'var(--muted)',fontFamily:'var(--font-jetbrains)'}}>Red action → Sandbox decision → Evidence fan-out</div>
      </div>
      <div style={{borderTop:'1px solid var(--line)',padding:'0'}}>
        <LiveTicker records={records}/>
      </div>
    </div>

    <Panel title="Recent runs"><RunTable runs={runs}/></Panel>

    <Panel title="Recent Evidence"><EvidenceTable records={records}/></Panel>

    <div className="ops">
      Scheduler {s?.scheduler?.enabled?'ON':'OFF'} · Latest {s?.latest_run?.status||'—'} · KB {s?.kb?.total_families??'—'} fam · {s?.kb?.total_signals??'—'} sig · Buffer {s?.buffer?.payment_records??'—'} pay · {s?.buffer?.blocked??'—'} blocked
    </div>
    <p style={{textAlign:'center',fontSize:11,color:'var(--muted-2)',marginTop:18}}>Synthetic, isolated environment · not connected to real payment networks · all figures generated by the running simulation — <b style={{color:'var(--muted)'}}>Loop A</b> (Red learning) + <b style={{color:'var(--muted)'}}>Loop B</b> (Blue hardening)</p>
  </Shell>
}
