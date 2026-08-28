'use client'
import {useEffect,useState,useRef} from 'react'
import {Shell,PageHead,Badge,Empty} from './dashboard'

interface ChatMessage {
  role: 'user'|'assistant'
  content: string
  proposal?: any
}

interface KBFamily {
  attack_id: string
  name: string
  lifecycle_stage: string
  simulation_type: string
  surface: string
}

const SUGGESTIONS = [
  "Design an attack that bypasses AML transaction monitoring using synthetic identities combined with real device fingerprints",
  "Create a novel attack on open banking APIs that exfiltrates data through legitimate-looking payment initiation requests",
  "Build an adaptive attack that learns the ML model's scoring threshold and stays just below it across multiple surfaces",
  "Design a social engineering attack that exploits the gap between KYC verification and ongoing transaction monitoring",
  "Create an attack that poisons the fraud detection model's training data by injecting carefully crafted hard negatives",
  "Design a multi-surface attack that starts with account takeover, pivots to device spoofing, and culminates in high-value payment fraud",
]

export function AttackDesigner(){
  const[messages,setMessages]=useState<ChatMessage[]>([])
  const[input,setInput]=useState('')
  const[loading,setLoading]=useState(false)
  const[error,setError]=useState('')
  const[families,setFamilies]=useState<KBFamily[]>([])
  const[focusFamily,setFocusFamily]=useState('')
  const[endRef,setEndRef]=useState<HTMLDivElement|null>(null)
  const[showSidebar,setShowSidebar]=useState(true)

  useEffect(()=>{
    fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL||'http://localhost:8000'}/api/redteam/families`)
      .then(r=>r.json())
      .then(setFamilies)
      .catch(()=>{})
  },[])

  useEffect(()=>{
    endRef?.scrollIntoView({behavior:'smooth'})
  },[messages,endRef])

  const send=async(prompt?:string)=>{
    const text=(prompt||input).trim()
    if(!text||loading)return
    setInput('')
    setError('')
    setMessages(prev=>[...prev,{role:'user',content:text}])
    setLoading(true)

    try{
      const res=await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL||'http://localhost:8000'}/api/redteam/propose`,{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({prompt:text,focus_family:focusFamily||undefined})
      })
      if(!res.ok){
        const err=await res.json().catch(()=>({detail:'Request failed'}))
        throw new Error(err.detail||`HTTP ${res.status}`)
      }
      const data=await res.json()
      setMessages(prev=>[...prev,{
        role:'assistant',
        content:data.raw_llm_output,
        proposal:data.proposal
      }])
    }catch(e:any){
      setError(e.message||'Failed to generate proposal')
      setMessages(prev=>[...prev,{
        role:'assistant',
        content:`⚠ Error: ${e.message||'Failed to connect to LLM. Make sure OPENROUTER_API_KEY is set.'}`
      }])
    }finally{
      setLoading(false)
    }
  }

  return<Shell>
    <PageHead eyebrow="Red team / Attack Designer" title="Attack Designer" subtitle="Chat with the AI to design novel adversarial attacks using your knowledge base."/>

    <div style={{display:'flex',gap:16,height:'calc(100vh - 200px)',minHeight:500}}>
      {/* Sidebar — KB Families */}
      {showSidebar&&<aside style={{width:260,flexShrink:0,overflow:'auto',border:'1px solid #e5e7eb',borderRadius:12,background:'#fff',padding:14}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:12}}>
          <span style={{font:'600 12px var(--font-jetbrains)',color:'#1a1a2e',textTransform:'uppercase',letterSpacing:'0.08em'}}>KB Families</span>
          <span style={{font:'10px var(--font-jetbrains)',color:'#9ca3af'}}>{families.length}</span>
        </div>
        <button
          className={`chip ${!focusFamily?'selected':''}`}
          style={{width:'100%',textAlign:'left',marginBottom:6}}
          onClick={()=>setFocusFamily('')}
        >All families (diverse)</button>
        <div style={{display:'flex',flexDirection:'column',gap:4,maxHeight:400,overflow:'auto'}}>
          {families.map(f=><button
            key={f.attack_id}
            className={`chip ${focusFamily===f.attack_id?'selected':''}`}
            style={{textAlign:'left',width:'100%'}}
            onClick={()=>setFocusFamily(f.focus_family===f.attack_id?'':f.attack_id)}
          >
            <strong style={{fontSize:11}}>{f.attack_id}</strong>
            <small style={{fontSize:10,color:'#9ca3af',display:'block',marginTop:2}}>{f.name?.slice(0,40)}</small>
          </button>)}
        </div>
      </aside>}

      {/* Main chat area */}
      <div style={{flex:1,display:'flex',flexDirection:'column',border:'1px solid #e5e7eb',borderRadius:12,background:'#fff',overflow:'hidden'}}>
        {/* Messages */}
        <div style={{flex:1,overflow:'auto',padding:20}}>
          {messages.length===0&&<div style={{textAlign:'center',padding:'60px 20px'}}>
            <div style={{fontSize:48,marginBottom:16}}>🎯</div>
            <h2 style={{fontSize:20,fontWeight:600,color:'#1a1a2e',margin:'0 0 8px'}}>Attack Designer</h2>
            <p style={{color:'#6b7280',fontSize:14,margin:'0 0 24px',maxWidth:480,marginInline:'auto'}}>
              Describe an attack scenario and the AI will design a novel adversarial payload using your knowledge base of 57 attack families.
            </p>
            <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(280px,1fr))',gap:10,maxWidth:700,margin:'0 auto'}}>
              {SUGGESTIONS.map((s,i)=><button
                key={i}
                onClick={()=>send(s)}
                style={{
                  textAlign:'left',padding:'12px 14px',border:'1px solid #e5e7eb',borderRadius:10,
                  background:'#f9fafb',cursor:'pointer',fontSize:12,color:'#374151',lineHeight:1.5,
                  transition:'border-color 0.15s'
                }}
                onMouseEnter={e=>(e.currentTarget.style.borderColor='#dc2626')}
                onMouseLeave={e=>(e.currentTarget.style.borderColor='#e5e7eb')}
              >{s}</button>)}
            </div>
          </div>}

          {messages.map((msg,i)=><div key={i} style={{marginBottom:20}}>
            <div style={{display:'flex',gap:10,alignItems:'flex-start'}}>
              <div style={{
                width:32,height:32,borderRadius:8,flexShrink:0,
                background:msg.role==='user'?'#dc2626':'#1a1a2e',
                display:'grid',placeItems:'center',color:'#fff',fontSize:14,fontWeight:700
              }}>{msg.role==='user'?'U':'AI'}</div>
              <div style={{flex:1,minWidth:0}}>
                <div style={{fontSize:11,color:'#9ca3af',marginBottom:4,fontFamily:'var(--font-jetbrains)'}}>
                  {msg.role==='user'?'You':'Attack Designer'}
                </div>
                {msg.proposal?<ProposalCard proposal={msg.proposal}/>:
                  <div style={{fontSize:13,color:'#374151',lineHeight:1.7,whiteSpace:'pre-wrap',wordBreak:'break-word'}}>
                    {msg.content}
                  </div>
                }
              </div>
            </div>
          </div>)}

          {loading&&<div style={{display:'flex',gap:10,alignItems:'flex-start',marginBottom:20}}>
            <div style={{width:32,height:32,borderRadius:8,background:'#1a1a2e',display:'grid',placeItems:'center',color:'#fff',fontSize:14,fontWeight:700}}>AI</div>
            <div>
              <div style={{fontSize:11,color:'#9ca3af',marginBottom:4,fontFamily:'var(--font-jetbrains)'}}>Attack Designer</div>
              <div style={{padding:'12px 16px',background:'#f9fafb',borderRadius:10,fontSize:13,color:'#6b7280'}}>
                <span style={{animation:'pulse 1.5s infinite'}}>●</span> Designing attack proposal...
              </div>
            </div>
          </div>}

          {error&&!loading&&<div className="error" style={{background:'#fef2f2',border:'1px solid #fecaca',borderRadius:8,padding:12,marginBottom:16}}>
            ⚠ {error}
          </div>}

          <div ref={setEndRef}/>
        </div>

        {/* Input bar */}
        <div style={{borderTop:'1px solid #e5e7eb',padding:'14px 20px',background:'#fafafa'}}>
          {focusFamily&&<div style={{marginBottom:8}}>
            <span style={{fontSize:11,color:'#6b7280',fontFamily:'var(--font-jetbrains)'}}>Focusing on: </span>
            <Badge tone="running">{focusFamily}</Badge>
            <button onClick={()=>setFocusFamily('')} style={{marginLeft:8,border:0,background:'none',color:'#9ca3af',cursor:'pointer',fontSize:11}}>× clear</button>
          </div>}
          <div style={{display:'flex',gap:10}}>
            <input
              value={input}
              onChange={e=>setInput(e.target.value)}
              onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}}}
              placeholder="Describe an attack scenario..."
              disabled={loading}
              style={{
                flex:1,border:'1px solid #e5e7eb',borderRadius:10,padding:'10px 14px',
                fontSize:13,fontFamily:'var(--font-jetbrains)',background:'#fff',
                outline:'none'
              }}
            />
            <button
              className="button"
              onClick={()=>send()}
              disabled={loading||!input.trim()}
              style={{minWidth:80}}
            >{loading?'...':'Generate'}</button>
          </div>
        </div>
      </div>
    </div>
  </Shell>
}


function ProposalCard({proposal}:{proposal:any}){
  const[expanded,setExpanded]=useState(false)
  return<div style={{border:'1px solid #e5e7eb',borderRadius:12,background:'#fff',overflow:'hidden',marginTop:8}}>
    <div style={{padding:'14px 16px',borderBottom:'1px solid #f3f4f6',background:'#fef2f2'}}>
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
        <h3 style={{margin:0,fontSize:15,fontWeight:600,color:'#1a1a2e'}}>{proposal.attack_name}</h3>
        <Badge tone="running">NEW</Badge>
      </div>
      <p style={{margin:'6px 0 0',fontSize:12,color:'#6b7280',lineHeight:1.5}}>{proposal.description}</p>
    </div>

    <div style={{padding:'14px 16px'}}>
      <div style={{display:'flex',flexWrap:'wrap',gap:8,marginBottom:14}}>
        <div className="stat" style={{minWidth:100}}><span>Surface</span><strong>{proposal.target_surface}</strong></div>
        <div className="stat" style={{minWidth:100}}><span>Stage</span><strong>{proposal.lifecycle_stage}</strong></div>
        {proposal.attack_family&&<div className="stat" style={{minWidth:100}}><span>Family</span><strong>{proposal.attack_family}</strong></div>}
      </div>

      {/* Attack Flow */}
      {proposal.attack_flow?.length>0&&<div style={{marginBottom:14}}>
        <div style={{fontSize:11,color:'#6b7280',marginBottom:6,fontFamily:'var(--font-jetbrains)',textTransform:'uppercase',letterSpacing:'0.06em'}}>Attack Flow</div>
        <ol style={{margin:0,paddingLeft:18,fontSize:12,color:'#374151',lineHeight:1.8}}>
          {proposal.attack_flow.map((s:string,i:number)=><li key={i}>{s}</li>)}
        </ol>
      </div>}

      {/* Payloads */}
      {proposal.payloads?.length>0&&<div style={{marginBottom:14}}>
        <div style={{fontSize:11,color:'#6b7280',marginBottom:6,fontFamily:'var(--font-jetbrains)',textTransform:'uppercase',letterSpacing:'0.06em'}}>Payloads</div>
        {proposal.payloads.map((p:any,i:number)=><div key={i} style={{padding:'8px 10px',background:'#f9fafb',borderRadius:8,marginBottom:6,fontSize:12}}>
          <strong>{p.type}</strong>: {p.description}
          {p.amount&&<span style={{color:'#6b7280',marginLeft:8}}>Amount: {p.amount}</span>}
          {p.evasion&&<div style={{color:'#dc2626',marginTop:4,fontSize:11}}>Evasion: {p.evasion}</div>}
        </div>)}
      </div>}

      {/* Controls Targeted */}
      {proposal.controls_targeted?.length>0&&<div style={{marginBottom:14}}>
        <div style={{fontSize:11,color:'#6b7280',marginBottom:6,fontFamily:'var(--font-jetbrains)',textTransform:'uppercase',letterSpacing:'0.06em'}}>Controls Targeted</div>
        <div className="chips">{proposal.controls_targeted.map((c:string)=><Badge key={c}>{c}</Badge>)}</div>
      </div>}

      {/* Novelty */}
      {proposal.novelty_notes&&<div style={{marginBottom:14,padding:'10px 12px',background:'#f0fdf4',borderRadius:8,fontSize:12,color:'#166534',lineHeight:1.6}}>
        <strong>Novelty:</strong> {proposal.novelty_notes}
      </div>}

      {/* KB References */}
      {proposal.kb_references?.length>0&&<div>
        <div style={{fontSize:11,color:'#6b7280',marginBottom:6,fontFamily:'var(--font-jetbrains)',textTransform:'uppercase',letterSpacing:'0.06em'}}>KB References</div>
        <div className="chips">{proposal.kb_references.map((r:string)=><Badge key={r} tone="muted">{r}</Badge>)}</div>
      </div>}

      {/* Expand raw */}
      <button
        onClick={()=>setExpanded(!expanded)}
        style={{marginTop:12,border:0,background:'none',color:'#9ca3af',cursor:'pointer',fontSize:11,fontFamily:'var(--font-jetbrains)'}}
      >{expanded?'▾ Hide raw JSON':'▸ Show raw JSON'}</button>
      {expanded&&<pre className="json" style={{marginTop:8}}>{JSON.stringify(proposal,null,2)}</pre>}
    </div>
  </div>
}
