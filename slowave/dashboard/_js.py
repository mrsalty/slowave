"""App JS for the Slowave dashboard. Edit this file, not app.py."""

_APP_JS = r'''
const REFRESH_MS=__REFRESH_MS__;
const ALLOW_ACTIONS=__ALLOW_ACTIONS__;

const statusColor={active:"#3ecf6e",needs_review:"#f5b942",contradicted:"#f04e6a",superseded:"#9d71f0",archived:"#5a6e91"};
const relColor={reinforces:"#3ecf6e",refines:"#4f9bff",contradicts:"#f04e6a",supersedes:"#f5b942",related_to:"#5a6e91",part_of:"#34c4c4"};
const relLabel={reinforces:"reinforces",refines:"refines",contradicts:"contradicts",supersedes:"supersedes",related_to:"related",part_of:"part of"};

function truncContent(s,max){
  if(!s||s.length<=max)return esc(s);
  return '<span title="'+esc(s)+'">'+esc(s.slice(0,max-3))+'<span style="color:var(--muted)"> …</span></span>';
}
function esc(s){return String(s??"")
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
  .replace(/"/g,"&quot;").replace(/'/g,"&#39;");}
function fmtBytes(n){n=Number(n||0);if(n<1024)return n+" B";if(n<1048576)return (n/1024).toFixed(1)+" KB";return (n/1048576).toFixed(2)+" MB";}
function fmtTs(ts){if(!ts)return "—";return new Date(Number(ts)*1000).toLocaleString();}
function fmtTsCompact(ts){
  if(!ts)return "—";
  const d=new Date(Number(ts)*1000);
  return d.toLocaleTimeString();
}
function fmtTsCompactSub(ts){
  if(!ts)return "";
  return new Date(Number(ts)*1000).toLocaleDateString();
}
function fmtDate(ts){if(!ts)return "—";return new Date(Number(ts)*1000).toLocaleDateString();}
function age(s){s=Number(s||0);if(s<60)return s+"s";if(s<3600)return Math.floor(s/60)+"m";if(s<86400)return Math.floor(s/3600)+"h "+Math.floor((s%3600)/60)+"m";return Math.floor(s/86400)+"d";}
function dur(s){if(s==null||s===undefined)return "open";s=Number(s);if(s<1)return "<1s";return age(s);}
function num(n){return Number(n||0).toLocaleString();}
async function getJSON(url){const r=await fetch(url);return await r.json();}
async function postJSON(url,obj){const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(obj)});return await r.json();}

// ── TOOLTIP ──
const ttEl=document.getElementById("tooltip");
function showTip(e,html){ttEl.innerHTML=html;ttEl.style.display="block";moveTip(e);}
function moveTip(e){if(!e||typeof e.clientX!="number"||typeof e.clientY!="number"){ttEl.style.left="50%";ttEl.style.top="50%";return}const x=e.clientX,y=e.clientY,w=ttEl.offsetWidth,h=ttEl.offsetHeight;ttEl.style.left=Math.min(x+12,window.innerWidth-w-8)+"px";ttEl.style.top=Math.min(y+12,window.innerHeight-h-8)+"px";}
function hideTip(){ttEl.style.display="none";}
document.addEventListener("mousemove",moveTip);

// ── TABS ──
document.querySelectorAll(".tab").forEach(b=>b.onclick=()=>{
  document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));
  document.querySelectorAll(".section").forEach(x=>x.classList.remove("active"));
  b.classList.add("active");
  document.getElementById(b.dataset.tab).classList.add("active");
  const tab=b.dataset.tab;
  if(tab==="overview")renderPulse();
  else if(tab==="schemas")loadSchemas();
  else if(tab==="graph")loadGraph();
  else if(tab==="worker")loadWorker();
  else if(tab==="generalization")loadGeneralization();
  else if(tab==="db")loadDbHealth();
  else if(tab==="supersessions")loadSupersessions();
});

// ── HELPERS ──
function pill(status){
  return `<span class="pill pill-${esc(status)}">${esc(status)}</span>`;
}
function salBar(val,max){
  const pct=Math.min(100,Math.round(val/Math.max(0.001,max)*100));
  return `<div class="sal-bar-wrap"><div class="sal-bar-track"><div class="sal-bar-fill" style="width:${pct}%"></div></div></div>`;
}
function confBar(val){
  const pct=Math.round(val*100);
  return `<div class="conf-bar"><div class="conf-track"><div class="conf-fill" style="width:${pct}%"></div></div><span style="font-size:11px;color:var(--muted)">${pct}%</span></div>`;
}
function table(head,rows,rawCols=[]){
  if(!rows.length)return emptyState("No data.");
  const ths=head.map(h=>`<th>${esc(h)}</th>`).join("");
  const trs=rows.map((r,ri)=>{
    const tds=r.map((c,ci)=>`<td>${rawCols.includes(ci)?c:esc(c)}</td>`).join("");
    return `<tr>${tds}</tr>`;
  }).join("");
  return `<div class="table-wrap"><table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table></div>`;
}
function emptyState(msg,icon="📭"){
  return `<div class="empty-state"><div class="es-icon">${icon}</div><div class="es-text">${esc(msg)}</div></div>`;
}

// ── OVERVIEW ──
async function loadStatus(){
  const d=await getJSON("/api/status");
  window.lastStatus=d;
  document.getElementById("dbPath").textContent=d.db_path;
  document.getElementById("dbPath").title=d.db_path;
  document.getElementById("lastUpdated").textContent="Updated "+new Date().toLocaleTimeString();

  // Init salience slider once we have data
  if(!window.salienceSliderInitialized){initSalienceSlider(d);}

  // Populate scope dropdown
  const scopeSel=document.getElementById("graphScope");
  if(scopeSel&&d.scopes){
    const val=scopeSel.value;
    scopeSel.innerHTML='<option value="">(all scopes)</option>'+d.scopes.map(s=>`<option value="${esc(s.scope)}">${esc(s.scope)} (${s.sessions})</option>`).join("");
    scopeSel.value=val;
  }

  const s=d.stats||{}, h=d.schema_health||{};
  const maxSal=Number(h?.active_salience?.max||1);

  // STAT CARDS
  const cards=[
    {icon:"💬",label:"Sessions",val:num(s.sessions),sub:"total",accent:"var(--cyan)"},
    {icon:"⚡",label:"Raw events",val:num(s.raw_events),sub:"logged",accent:"var(--blue)"},
    {icon:"🎞",label:"Episodes",val:num(s.episodes),sub:"formed",accent:"var(--blue)"},
    {icon:"🔵",label:"Prototypes",val:num(s.prototypes),sub:"semantic",accent:"var(--purple)"},
    {icon:"📖",label:"Schemas",val:num(s.schemas),sub:`<span style="display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap"><span style="display:inline-flex;align-items:center;gap:4px"><span style="width:8px;height:8px;border-radius:50%;background:var(--green);display:inline-block;flex-shrink:0"></span><span style="font-size:11px;color:var(--text)">${num(h.active_schemas)} active</span></span><span style="display:inline-flex;align-items:center;gap:4px"><span style="width:8px;height:8px;border-radius:50%;background:var(--amber);display:inline-block;flex-shrink:0"></span><span style="font-size:11px;color:var(--text)">${num(h.needs_review_schemas)} needs review</span></span></span>`,accent:"var(--green)",raw:true},
    {icon:"🕸",label:"Edges",val:num(s.edges),sub:"prototype",accent:"var(--purple)"},
    {icon:"🔗",label:"Relations",val:num(s.schema_relations),sub:"schema",accent:"var(--purple)"},
    {icon:"🗣",label:"Feedback",val:num(s.feedback_events),sub:"events",accent:"var(--cyan)"},
    {icon:"🌐",label:"Promoted",val:num(s.promoted_schemas),sub:"stage ≥ 1",accent:"var(--amber)"},
    {icon:"✨",label:"Global",val:num(s.global_schemas),sub:"stage 3",accent:"var(--green)"},
    {icon:"🗺",label:"Known scopes",val:num(s.known_scopes),sub:"registered",accent:"var(--cyan)"},
    {icon:"💾",label:"DB size",val:fmtBytes(d.db_size_bytes),sub:d.wal_size_bytes>0?"WAL: "+fmtBytes(d.wal_size_bytes):"",accent:"var(--muted)"},
  ];
  document.getElementById("statGrid").innerHTML=cards.map(c=>{
    return `<div class="stat-card" style="--accent:${c.accent}">
      <div class="sc-icon">${c.icon}</div>
      <div class="sc-label">${esc(c.label)}</div>
      <div class="sc-value">${c.raw?c.val:esc(String(c.val??0))}</div>
      <div class="sc-sub">${c.raw?c.sub:esc(c.sub||"")} </div>
    </div>`;
  }).join("");

  // ALERTS
  const warns=d.warnings||[];
  let alertHtml="";
  if(!d.db_exists){
    alertHtml=`<div class="alert alert-error"><span class="alert-icon">❌</span><div><b>Database not found</b><br>Path: ${esc(d.db_path)}</div></div>`;
  } else if(warns.length){
    alertHtml=`<div class="alert alert-warn"><span class="alert-icon">⚠️</span><div><b>${warns.length} warning${warns.length>1?"s":""}</b><ul>${warns.map(w=>`<li>${esc(w)}</li>`).join("")}</ul></div></div>`;
    // Update badge
    
  } else {
    alertHtml=`<div class="alert alert-ok" style="align-items:center"><span class="alert-icon" style="display:flex;align-items:center;justify-content:center;width:16px;height:16px"><span style="width:10px;height:10px;border-radius:50%;background:var(--green);display:block;flex-shrink:0"></span></span><div><b>All systems healthy</b></div></div>`;
    
  }
  document.getElementById("alertArea").innerHTML=alertHtml;

  // SCHEMA HEALTH PANEL
  const byStatus=h.schemas_by_status||{};
  const total=Math.max(1,h.schemas_total||0);
  const statusOrder=["active","needs_review","contradicted","superseded","archived"];
  const barSegs=statusOrder.map(st=>{
    const n=byStatus[st]||0;
    const pct=Math.round(n/total*100);
    return n>0?`<div class="status-bar-seg" style="width:${pct}%;background:${statusColor[st]||"#5a6e91"}"
      title="${st}: ${n}"></div>`:"";
  }).join("");
  const sal=h.active_salience||{};
  const avgSal=Number(sal.avg||0);
  const maxSalience=Number(sal.max||0);
  const salPct=maxSalience>0?Math.round(avgSal/maxSalience*100):0;
  const lastConsolidated=d.last_consolidation_ts?"Last session: "+fmtTs(d.last_consolidation_ts):"No sessions yet";
  document.getElementById("schemaHealthPanel").innerHTML=`
    <div class="status-bar">${barSegs||"<div class=\"status-bar-seg\" style=\"width:100%;background:var(--line)\"></div>"}</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin:8px 0">
      ${statusOrder.map(st=>{
        const n=byStatus[st]||0;
        return n>0?`<span class="pill pill-${st}">${st} ${num(n)}</span>`:"";
      }).join("")}
    </div>
    <div style="margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px">
      <div><span style="color:var(--muted)">Avg salience</span><br><b>${avgSal.toFixed(3)}</b></div>
      <div><span style="color:var(--muted)">Max salience</span><br><b>${maxSalience.toFixed(3)}</b></div>
      <div><span style="color:var(--muted)">Duplicates</span><br><b>${num(h.active_exact_duplicate_rows||0)}</b></div>
    </div>
    <div style="margin-top:10px;font-size:11px;color:var(--muted)">${esc(lastConsolidated)}</div>
  `;

  // DAEMON HEALTH PANEL
  const dmn=d.daemon||{};
  const daemonRunning=dmn.running===true;
  const daemonBadge=daemonRunning
    ?`<span class="pill pill-ok">&#x2022; running</span>`
    :`<span class="pill pill-orphan">&#x25cf; stopped</span>`;
  const daemonUrl=dmn.url||"http://127.0.0.1:8766/mcp";
  const daemonSessions=Number(dmn.active_sessions||0);
  const daemonVersion=dmn.version?"v"+dmn.version:"";
  document.getElementById("daemonPanel").innerHTML=daemonRunning?`
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
      ${daemonBadge}
      <span style="font-size:12px;color:var(--muted)">${esc(daemonVersion)}</span>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;margin-bottom:10px">
      <div><span style="color:var(--muted)">Endpoint</span><br><code style="font-size:11px">${esc(daemonUrl)}</code></div>
      <div><span style="color:var(--muted)">Active sessions</span><br><b>${daemonSessions}</b></div>
    </div>
    <div style="font-size:11px;color:var(--muted)">
      <a href="${esc(dmn.health_url||'http://127.0.0.1:8766/health')}" target="_blank" style="color:var(--blue)">health endpoint &#x2197;</a>
    </div>`:daemonRunning===false?`
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
      ${daemonBadge}
    </div>
    <div style="color:var(--muted);font-size:13px;margin-bottom:8px">HTTP MCP daemon is not running.</div>
    <div style="font-size:12px">Start it with: <code>slowave serve start</code></div>`:"";

  // RECENT SESSIONS
  const sess=d.recent_sessions||[];
  if(!sess.length){
    document.getElementById("recentSessions").innerHTML=emptyState("No sessions yet.","💬");
  } else {
    document.getElementById("recentSessions").innerHTML=table(
      ["Session","Agent","Scope","Started","Duration","Events","Ep."],
      sess.map(r=>[
        `<span onclick="loadSessionTimeline('${esc(r.id)}')" style="cursor:pointer;color:var(--blue);font-family:monospace;font-size:11px" title="Click to replay session">${esc((r.id||"").slice(0,12))}…</span>`,
        r.agent||"—",r.scope_id||"(none)",
        fmtTs(r.started_ts),dur(r.duration_seconds),
        num(r.events),num(r.episodes)
      ]),
      [0]
    );
  }

  // SCOPES
  const scopes=d.scopes||[];
  if(!scopes.length){
    document.getElementById("scopesPanel").innerHTML=emptyState("No scopes.","🗂");
  } else {
    document.getElementById("scopesPanel").innerHTML=table(
      ["Scope","Sessions"],
      scopes.map(r=>[r.scope,num(r.sessions)])
    );
  }

  // PULSE GRAPH — refresh on every status poll cycle
  renderPulse();
  renderSalienceHistogram();
}

async function renderPulse(){
  try{
    const d=await getJSON("/api/pulse?hours=3&bucket_m=15");
    const canvas=document.getElementById("pulseCanvas");
    const tooltip=document.getElementById("pulseTooltip");
    const stats=document.getElementById("pulseStats");
    if(!canvas)return;

    const DPR=window.devicePixelRatio||1;
    const W=canvas.parentElement.clientWidth;
    if(W<=0)return;
    const H=110;
    canvas.width=Math.round(W*DPR);
    canvas.height=Math.round(H*DPR);
    canvas.style.width=W+"px";
    canvas.style.height=H+"px";
    const ctx=canvas.getContext("2d");
    ctx.scale(DPR,DPR);
    ctx.clearRect(0,0,W,H);

    // ── channel definitions ───────────────────────────────────────────────────
    const CHANNELS=[
      {key:"raw_events",label:"raw events",color:"#10b981",gc:"rgba(16,185,129,"},
      {key:"episodes",  label:"episodes",  color:"#fbbf24",gc:"rgba(251,191,36,"},
      {key:"schemas",   label:"schemas",   color:"#3b82f6",gc:"rgba(59,130,246,"},
    ];
    const channels=d.channels||{raw_events:d.buckets||[],episodes:[],schemas:[]};
    const allBuckets=channels[CHANNELS[0].key]||[];
    const N=allBuckets.length;

    if(!N||!d.global_max){
      const bl=H-18;
      ctx.strokeStyle="rgba(56,189,248,.18)";ctx.lineWidth=0.8;ctx.setLineDash([4,7]);
      ctx.beginPath();ctx.moveTo(0,bl);ctx.lineTo(W,bl);ctx.stroke();ctx.setLineDash([]);
      ctx.fillStyle="#5a7ab5";ctx.font="12px system-ui,sans-serif";ctx.textAlign="center";
      ctx.fillText("Flatline \u2014 no events in the last "+d.window_hours+"h",W/2,bl-10);
      canvas.onmousemove=null;canvas.onmouseleave=null;stats.innerHTML="";return;
    }

    // ── layout ───────────────────────────────────────────────────────────────
    const PAD_L=4,PAD_R=4,PAD_T=8,PAD_B=18;
    const IW=W-PAD_L-PAD_R;
    const IH=H-PAD_T-PAD_B;
    const baseline=H-PAD_B;
    const step=IW/(N-1||1);
    const gmax=d.global_max||1;
    const amp=v=>Math.sqrt(v/gmax)*IH*0.88;

    // ── Catmull-Rom spline ────────────────────────────────────────────────────
    function buildSpline(pts){
      const pp=[pts[0],...pts,pts[pts.length-1]];
      ctx.moveTo(pp[1].x,pp[1].y);
      for(let i=1;i<pp.length-2;i++){
        const p0=pp[i-1],p1=pp[i],p2=pp[i+1],p3=pp[i+2];
        const d1=Math.hypot(p1.x-p0.x,p1.y-p0.y)||1;
        const d2=Math.hypot(p2.x-p1.x,p2.y-p1.y)||1;
        const d3=Math.hypot(p3.x-p2.x,p3.y-p2.y)||1;
        ctx.bezierCurveTo(
          p1.x+(p2.x-p0.x)/6*(d1/(d1+d2)),p1.y+(p2.y-p0.y)/6*(d1/(d1+d2)),
          p2.x-(p3.x-p1.x)/6*(d2/(d2+d3)),p2.y-(p3.y-p1.y)/6*(d2/(d2+d3)),
          p2.x,p2.y);
      }
    }

    // ── grid + baseline ───────────────────────────────────────────────────────
    ctx.strokeStyle="rgba(20,35,65,.8)";ctx.lineWidth=0.5;
    [0.25,0.5,0.75,1].forEach(f=>{
      const gy=baseline-Math.sqrt(f)*IH*0.88;
      ctx.beginPath();ctx.moveTo(0,gy);ctx.lineTo(W,gy);ctx.stroke();
    });
    ctx.strokeStyle="rgba(56,189,248,.10)";ctx.lineWidth=0.5;
    ctx.beginPath();ctx.moveTo(0,baseline);ctx.lineTo(W,baseline);ctx.stroke();

    // ── draw channels ─────────────────────────────────────────────────────────
    const allPts={};
    CHANNELS.forEach(ch=>{
      const bkts=channels[ch.key]||[];
      if(!bkts.length)return;
      const pts=bkts.map((b,i)=>({x:PAD_L+i*step,y:baseline-amp(b.n),n:b.n,ts:b.ts}));
      allPts[ch.key]=pts;
      if(!bkts.some(b=>b.n>0))return;
      // Faint area fill
      const gr=ctx.createLinearGradient(0,PAD_T,0,baseline);
      gr.addColorStop(0,ch.gc+"0.06)");gr.addColorStop(1,ch.gc+"0)");
      ctx.beginPath();buildSpline(pts);
      ctx.lineTo(pts[pts.length-1].x,baseline);ctx.lineTo(pts[0].x,baseline);ctx.closePath();
      ctx.fillStyle=gr;ctx.fill();
      // Thin lines: glow pass then crisp pass
      [{blur:5,w:1.2,a:.5},{blur:0,w:0.8,a:1}].forEach(({blur,w,a})=>{
        ctx.save();
        ctx.shadowColor=ch.gc+a+")";ctx.shadowBlur=blur;
        ctx.strokeStyle=ch.color;ctx.lineWidth=w;ctx.lineJoin="round";ctx.lineCap="round";
        ctx.beginPath();buildSpline(pts);ctx.stroke();
        ctx.restore();
      });
    });

    // ── time axis ─────────────────────────────────────────────────────────────
    ctx.fillStyle="rgba(80,100,140,.6)";
    ctx.font="10px system-ui,sans-serif";ctx.textAlign="center";
    const labelStep=Math.ceil(N/6);
    allBuckets.forEach((b,i)=>{
      if(i%labelStep!==0&&i!==N-1)return;
      ctx.fillText(new Date(b.ts*1000).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}),
        Math.min(W-18,Math.max(18,PAD_L+i*step)),H-3);
    });

    // ── hover ─────────────────────────────────────────────────────────────────
    canvas.onmousemove=function(e){
      const rect=canvas.getBoundingClientRect();
      const mx=e.clientX-rect.left;
      const idx=Math.min(N-1,Math.max(0,Math.round((mx-PAD_L)/step)));
      const rows=CHANNELS.map(ch=>{
        const b=(channels[ch.key]||[])[idx];
        return`<span style='color:${ch.color}'>\u25cf</span> ${ch.label}: <b>${b?b.n:0}</b>`;
      }).join("<br>");
      const ts=allBuckets[idx]?.ts;
      const t2=ts?new Date(ts*1000).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}):"";
      tooltip.style.display="block";
      tooltip.style.left=Math.min(W-70,Math.max(40,PAD_L+idx*step))+"px";
      tooltip.style.top="4px";
      tooltip.style.transform="translateX(-50%)";
      tooltip.innerHTML=`<div style='font-size:10px;color:var(--muted);margin-bottom:3px'>${t2}</div>${rows}`;
    };
    canvas.onmouseleave=function(){tooltip.style.display="none";};

    // ── stats footer ──────────────────────────────────────────────────────────
    const totals=CHANNELS.map(ch=>{
      const sum=(channels[ch.key]||[]).reduce((a,b)=>a+b.n,0);
      return`<span style='color:${ch.color}'>\u25cf ${ch.label}</span> <b>${sum}</b>`;
    }).join(" &nbsp;\u00b7&nbsp; ");
    stats.innerHTML=`<span style='color:var(--muted)'>${d.window_hours}h &nbsp;\u00b7&nbsp; ${d.bucket_minutes}m buckets</span>&nbsp;&nbsp;${totals}`;
  }catch(e){console.error("pulse",e);}
}
function statusBreakdown(by){
  const statusOrder=["active","needs_review","contradicted","superseded","archived"];
  return statusOrder
    .filter(s=>by[s]>0)
    .map(s=>`<span class="pill pill-${s}" style="font-size:10px">${s[0].toUpperCase()} ${by[s]}</span>`)
    .join("");
}

// ── SCHEMAS ──
let schemaMaxSalience=1;
async function loadSchemas(){
  const el=document.getElementById("schemaTable");
  const ld=document.getElementById("schemaLoading");
  ld.classList.add("show");el.innerHTML="";
  document.getElementById("schemaDetail").innerHTML="";
  try{
    const st=document.getElementById("schemaStatus").value;
    const sc=encodeURIComponent(document.getElementById("schemaScope").value);
    const q=encodeURIComponent(document.getElementById("schemaQ").value);
    const lim=document.getElementById("schemaLimit").value;
    const d=await getJSON(`/api/schemas?limit=${lim}&status=${encodeURIComponent(st)}&scope=${sc}&q=${q}`);
    schemaMaxSalience=Math.max(1,...(d.schemas||[]).map(s=>s.salience));
    el.innerHTML=renderSchemasTable(d.schemas||[]);
    // attach expand handlers
    el.querySelectorAll("tr.expandable").forEach(tr=>{
      tr.addEventListener("click",()=>expandSchemaRow(tr,parseInt(tr.dataset.id)));
    });
  } finally{ld.classList.remove("show");}
}
function renderSchemasTable(schemas){
  if(!schemas.length)return emptyState("No schemas found.","📖");
  const rows=schemas.map(s=>{
    const salPct=Math.round(s.salience/Math.max(0.001,schemaMaxSalience)*100);
    const salHtml=`<span style="font-size:12px;font-weight:600">${s.salience.toFixed(3)}</span>
      <div class="sal-bar-track" style="width:50px;display:inline-block;vertical-align:middle;margin-left:4px">
        <div class="sal-bar-fill" style="width:${salPct}%"></div></div>`;
    const confHtml=confBar(s.confidence);
    const tagsHtml=(s.tags||[]).map(t=>`<span class="pill" style="font-size:10px">${esc(t)}</span>`).join("");
    const nr=s.needs_review?`<span class="pill pill-warn" style="font-size:10px">⚠ review</span>`:""
    const stage=s.generalization_stage||0;
    const stageBadge=stage>0?`<span class="gen-badge gen-${stage}" style="font-size:10px">${GEN_LABELS[stage]||stage}</span>`:`<span class="gen-badge gen-0" style="font-size:10px">SCOPED</span>`;
    return `<tr class="expandable" data-id="${s.schema_id}">
      <td><code style="font-size:11px">sch_${s.schema_id}</code></td>
      <td>${pill(s.status)}${nr}</td>
      <td>${salHtml}</td>
      <td>${confHtml}</td>
      <td>${stageBadge}</td>
      <td>${esc(s.schema_class||"—")}</td>
      <td>${esc(s.scope||"—")}</td>
      <td>${num(s.support_count)}</td>
      <td style="max-width:380px;word-break:break-word">${truncContent(s.content,120)}</td>
    </tr>`;
  }).join("");
  return `<table><thead><tr>
    <th>ID</th><th>Status</th><th>Salience</th><th>Confidence</th>
    <th>Stage</th><th>Class</th><th>Scope</th><th>Support</th><th>Content</th>
  </tr></thead><tbody>${rows}</tbody></table>`;
}
async function expandSchemaRow(tr,schemaId){
  // Toggle existing
  const nextTr=tr.nextElementSibling;
  if(nextTr&&nextTr.classList.contains("expand-row")){
    nextTr.remove();return;
  }
  const d=await getJSON(`/api/schemas/${schemaId}`);
  const s=d.schema;
  const evHtml=d.evidence&&d.evidence.length?`<div style="max-height:400px;overflow-y:auto">`+d.evidence.map((e,i)=>{
    const quote=e.quote||e.event_content||"";
    const evLink=e.raw_event_id?` <a href="#" onclick="loadEventInline(${e.raw_event_id},'evt_detail_${schemaId}_${i}');return false" style="color:var(--blue);font-size:12px">evt_${e.raw_event_id}</a>`:"";
    const sessLink=e.episode_session?` <a href="#" onclick="loadSessionTimeline('${esc(e.episode_session)}');return false" style="color:var(--cyan);font-size:11px">sess_${esc((e.episode_session||"").slice(0,12))}…</a>`:"";
    const kindBadge=e.episode_kind?`<span class="pill" style="font-size:9px;padding:1px 4px">${esc(e.episode_kind)}</span>`:"";
    const evMeta=e.event_type?`<span class="pill" style="font-size:10px">${esc(e.event_type)}</span> `:"";
    return `<div style="margin-bottom:6px;font-size:12px;padding:6px 8px;background:var(--panel2);border-radius:4px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:3px">
        <span style="color:var(--muted)">epi_${e.episode_id||"—"}</span>${kindBadge}${evLink}${sessLink}
        <span style="color:var(--green);font-size:11px">w${Number(e.weight||0).toFixed(3)}</span>
        ${evMeta}
      </div>
      ${quote?`<div style="color:var(--text);line-height:1.4;font-size:12px">${esc(quote.slice(0,300))}${quote.length>300?"…":""}</div>`:""}
      <div id="evt_detail_${schemaId}_${i}"></div>
    </div>`;}).join("")+`</div>`:`<em style="color:var(--muted)">No evidence.</em>`;
const outHtml=d.outgoing&&d.outgoing.length?table(["To","Relation","Confidence","Reason"],
    d.outgoing.map(e=>[`sch_${e.dst_schema_id}`,e.relation,Number(e.confidence||0).toFixed(2),e.reason||"—"])):"<em style='color:var(--muted)'>None.</em>";
  const inHtml=d.incoming&&d.incoming.length?table(["From","Relation","Confidence","Reason"],
    d.incoming.map(e=>[`sch_${e.src_schema_id}`,e.relation,Number(e.confidence||0).toFixed(2),e.reason||"—"])):"<em style='color:var(--muted)'>None.</em>";
  const expTr=document.createElement("tr");
  expTr.className="expand-row";
  const stage=s.generalization_stage||0;
  const genHtml=`<div class="detail-section"><h4>Generalization</h4>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
      ${genBadge(stage)}
      <span style="font-size:12px;color:var(--muted)">${GEN_DESC[stage]||""}</span>
    </div>
    ${stage>0?`
      ${genBreadthBar((s.scope_breadth_pct||0),"scope breadth")}
      ${genBreadthBar((s.scope_kind_breadth_pct||0),"kind breadth")}
      <div style="font-size:12px;color:var(--muted);margin-top:6px">
        ${(s.distinct_scope_count||0)} scope${s.distinct_scope_count!==1?"s":""} ·
        ${(s.distinct_scope_kind_count||0)} kind${s.distinct_scope_kind_count!==1?"s":""} ·
        ${(s.cross_scope_recall_count||0)} cross-scope recall${s.cross_scope_recall_count!==1?"s":""}
        ${(s.all_scopes||s.recalled_scopes||[]).length?`<div style="margin-top:4px;font-size:11px;color:var(--cyan)">Scopes: ${(s.all_scopes||s.recalled_scopes||[]).slice(0,12).map(sc=>typeof sc==="string"?`<span style="margin-right:6px">${esc(sc)}</span>`:`<span style="margin-right:6px" title="${esc(sc.kind||"")}">${esc(sc.id)}</span>`).join("")}${(s.all_scopes||s.recalled_scopes||[]).length>12?" …":""}</div>`:""}
      </div>`:"<div style='font-size:12px;color:var(--muted)'>Not yet recalled across multiple scopes.</div>"}
  </div>`;
  expTr.innerHTML=`<td colspan="9"><div class="expand-content">
    <div class="detail-section" style="margin-bottom:14px">
      <h4>Content</h4>
      <div style="font-size:13px;line-height:1.6;white-space:pre-wrap;word-break:break-word;padding:10px 12px;background:var(--panel2);border:1px solid var(--line);border-radius:var(--radius-sm)">${esc(s.content)}</div>
    </div>
    <div class="three-col">
      <div>
        <div class="detail-section"><h4>Facets</h4><pre class="code-block">${esc(JSON.stringify(s.facets,null,2))}</pre></div>
        ${genHtml}
      </div>
      <div>
        <div class="detail-section"><h4>Tags</h4>${(s.tags||[]).map(t=>`<span class="pill">${esc(t)}</span>`).join("")||"<em style='color:var(--muted)'>none</em>"}</div>
        <div class="detail-section" style="margin-top:10px"><h4>Timestamps</h4>
          <div style="font-size:12px;color:var(--muted)">First formed: ${fmtTs(s.first_formed_ts)}<br>Updated: ${fmtTs(s.last_updated_ts)}</div>
        </div>
      </div>
      <div><div class="detail-section"><h4>Outgoing relations</h4>${outHtml}</div>
           <div class="detail-section" style="margin-top:10px"><h4>Incoming relations</h4>${inHtml}</div></div>
    </div>
    <div class="detail-section"><h4>Evidence</h4>${evHtml}</div>
  </div></td>`;
  tr.after(expTr);
}

async function loadEventInline(eventId, slotId){
  const slot=document.getElementById(slotId);
  if(!slot)return;
  // Toggle
  if(slot.innerHTML&&!slot.innerHTML.includes("Loading")){
    slot.innerHTML="";return;
  }
  slot.innerHTML=`<div style="color:var(--muted);font-size:10px;padding:4px 0">Loading event…</div>`;
  try{
    const d=await getJSON(`/api/events/${eventId}`);
    if(d.error){slot.innerHTML=`<div style="color:var(--red);font-size:10px">${esc(d.error)}</div>`;return;}
    const ev=d.event;
    slot.innerHTML=`<div style="background:var(--panel3);border:1px solid var(--line2);border-radius:4px;padding:6px 10px;margin-top:4px;font-size:11px">
      <span class="pill" style="font-size:9px">${esc(ev.type||"?")}</span>
      <span style="color:var(--muted)">${fmtTsCompact(ev.ts)}</span>
      <span style="color:var(--muted)"> · session ${esc((ev.session_id||"").slice(0,12))}…</span>
      <div style="margin-top:4px;line-height:1.4;white-space:pre-wrap;word-break:break-word">${esc(ev.content||"")}</div>
    </div>`;
  }catch(e){slot.innerHTML=`<div style="color:var(--red);font-size:10px">${esc(String(e))}</div>`;}
}
window.loadEventInline = loadEventInline;

// ── WORKER ──
async function loadWorker(){
  const ld=document.getElementById("workerLoading");
  const tbl=document.getElementById("workerTable");
  ld.classList.add("show");tbl.innerHTML="";
  try{
    const lim=document.getElementById("workerLimit").value;
    const d=await getJSON(`/api/worker/runs?limit=${lim}`);
    const runs=d.runs||[];
    const sum=d.summary||{};

    // Stat cards
    const cards=[
      {icon:"🔄",label:"Total passes",val:num(sum.total_passes),accent:"var(--blue)"},
      {icon:"📖",label:"Schemas created",val:num(sum.total_schemas_created),accent:"var(--green)"},
      {icon:"🔁",label:"Reinforced",val:num(sum.total_schemas_reinforced),accent:"var(--cyan)"},
      {icon:"⏱",label:"Avg duration",val:(sum.avg_duration_ms||0).toFixed(0)+"ms",accent:"var(--amber)"},
      {icon:"📉",label:"Decayed",val:num(sum.total_schemas_decayed),accent:"var(--red)"},
      {icon:"🕐",label:"Last run",val:fmtTsCompact(sum.last_run_ts),sub:fmtTsCompactSub(sum.last_run_ts),accent:"var(--muted)",raw:true},
    ];
    document.getElementById("workerStatGrid").innerHTML=cards.map(c=>
      `<div class="stat-card" style="--accent:${c.accent}">
        <div class="sc-icon">${c.icon}</div>
        <div class="sc-label">${esc(c.label)}</div>
        <div class="sc-value">${c.raw?c.val:esc(String(c.val))}</div>
        ${c.sub?`<div class="sc-sub">${c.raw?c.sub:esc(c.sub)}</div>`:""}
      </div>`
    ).join("");

    renderWorkerChart(runs);

    // Table
    if(!runs.length){
      tbl.innerHTML=emptyState("No worker runs recorded yet. Start the worker with: slowave worker","🧠");
      return;
    }
    const heads=["#","Started","Duration","Trigger","Schemas +","~Reinf.","Protos","Decayed","Eps proc","Status"];
    const rows=runs.map(r=>[
      r.id,
      fmtTs(r.started_ts),
      r.duration_ms!=null?r.duration_ms+"ms":"—",
      r.triggered_by||"worker",
      `<b style="color:var(--green)">+${r.schemas_created||0}</b>`,
      num(r.schemas_reinforced||0),
      num(r.prototypes_processed||0),
      `<span style="color:var(--red)">-${r.schemas_decayed||0}</span>`,
      num(r.episodes_processed||0),
      r.error_text
        ?`<span class="pill pill-contradicted" title="${esc(r.error_text)}">error</span>`
        :`<span class="pill pill-active">ok</span>`,
    ]);
    const rawCols=[4,7,9];
    tbl.innerHTML=table(heads,rows,rawCols);
  }finally{ld.classList.remove("show");}
}

// ── WORKER CHART ──
function renderWorkerChart(runs){
  const canvas=document.getElementById("workerCanvas");
  const tooltip=document.getElementById("workerTooltip");
  const stats=document.getElementById("workerChartStats");
  if(!canvas)return;
  const pts_runs=runs.slice(0,50).reverse();
  const N=pts_runs.length;
  const DPR=window.devicePixelRatio||1;
  const W=canvas.parentElement.clientWidth||600;
  const H=120;
  canvas.width=Math.round(W*DPR);canvas.height=Math.round(H*DPR);
  canvas.style.width=W+"px";canvas.style.height=H+"px";
  const ctx=canvas.getContext("2d");
  ctx.scale(DPR,DPR);ctx.clearRect(0,0,W,H);
  const CHANNELS=[
    {key:"schemas_created",    label:"schemas +",  color:"#3b82f6",gc:"rgba(59,130,246,"},
    {key:"schemas_reinforced", label:"reinforced", color:"#10b981",gc:"rgba(16,185,129,"},
    {key:"schemas_decayed",    label:"decayed",    color:"#f04e6a",gc:"rgba(240,78,106,"},
  ];
  const gmax=Math.max(1,...pts_runs.flatMap(r=>CHANNELS.map(ch=>r[ch.key]||0)));
  const PAD_L=4,PAD_R=4,PAD_T=8,PAD_B=18;
  const IW=W-PAD_L-PAD_R,IH=H-PAD_T-PAD_B;
  const baseline=H-PAD_B;
  const step=N>1?IW/(N-1):IW;
  const amp=v=>Math.sqrt(v/gmax)*IH*0.88;
  if(!N){
    ctx.strokeStyle="rgba(56,189,248,.18)";ctx.lineWidth=0.8;ctx.setLineDash([4,7]);
    ctx.beginPath();ctx.moveTo(0,baseline);ctx.lineTo(W,baseline);ctx.stroke();ctx.setLineDash([]);
    ctx.fillStyle="#5a7ab5";ctx.font="12px system-ui,sans-serif";ctx.textAlign="center";
    ctx.fillText("No consolidation runs yet",W/2,baseline-10);
    stats.innerHTML="";return;
  }
  function buildSpline(pts){
    const pp=[pts[0],...pts,pts[pts.length-1]];
    ctx.moveTo(pp[1].x,pp[1].y);
    for(let i=1;i<pp.length-2;i++){
      const p0=pp[i-1],p1=pp[i],p2=pp[i+1],p3=pp[i+2];
      const d1=Math.hypot(p1.x-p0.x,p1.y-p0.y)||1;
      const d2=Math.hypot(p2.x-p1.x,p2.y-p1.y)||1;
      const d3=Math.hypot(p3.x-p2.x,p3.y-p2.y)||1;
      ctx.bezierCurveTo(
        p1.x+(p2.x-p0.x)/6*(d1/(d1+d2)),p1.y+(p2.y-p0.y)/6*(d1/(d1+d2)),
        p2.x-(p3.x-p1.x)/6*(d2/(d2+d3)),p2.y-(p3.y-p1.y)/6*(d2/(d2+d3)),
        p2.x,p2.y);
    }
  }
  function drawBase(){
    ctx.strokeStyle="rgba(20,35,65,.8)";ctx.lineWidth=0.5;
    [0.25,0.5,0.75,1].forEach(f=>{
      const gy=baseline-Math.sqrt(f)*IH*0.88;
      ctx.beginPath();ctx.moveTo(0,gy);ctx.lineTo(W,gy);ctx.stroke();
    });
    ctx.strokeStyle="rgba(56,189,248,.10)";ctx.lineWidth=0.5;
    ctx.beginPath();ctx.moveTo(0,baseline);ctx.lineTo(W,baseline);ctx.stroke();
  }
  const allPts={};
  CHANNELS.forEach(ch=>{
    allPts[ch.key]=pts_runs.map((r,i)=>({x:PAD_L+i*step,y:baseline-amp(r[ch.key]||0),n:r[ch.key]||0}));
  });
  function drawChannels(hoverIdx){
    CHANNELS.forEach(ch=>{
      const pts=allPts[ch.key]||[];
      if(!pts.some(p=>p.n>0))return;
      const gr=ctx.createLinearGradient(0,PAD_T,0,baseline);
      gr.addColorStop(0,ch.gc+"0.06)");gr.addColorStop(1,ch.gc+"0)");
      ctx.beginPath();buildSpline(pts);
      ctx.lineTo(pts[pts.length-1].x,baseline);ctx.lineTo(pts[0].x,baseline);ctx.closePath();
      ctx.fillStyle=gr;ctx.fill();
      [{blur:5,w:1.2,a:.5},{blur:0,w:0.8,a:1}].forEach(({blur,w,a})=>{
        ctx.save();ctx.shadowColor=ch.gc+a+")";ctx.shadowBlur=blur;
        ctx.strokeStyle=ch.color;ctx.lineWidth=w;ctx.lineJoin="round";ctx.lineCap="round";
        ctx.beginPath();buildSpline(pts);ctx.stroke();ctx.restore();
      });
      if(hoverIdx!=null){const p=pts[hoverIdx];if(p&&p.n>0){ctx.beginPath();ctx.arc(p.x,p.y,3,0,2*Math.PI);ctx.fillStyle=ch.color;ctx.fill();}}
    });
  }
  const labelStep=Math.ceil(N/6);
  function drawLabels(){
    ctx.fillStyle="rgba(80,100,140,.6)";ctx.font="10px system-ui,sans-serif";ctx.textAlign="center";
    pts_runs.forEach((r,i)=>{
      if(i%labelStep!==0&&i!==N-1)return;
      ctx.fillText(new Date(r.started_ts*1000).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}),
        Math.min(W-18,Math.max(18,PAD_L+i*step)),H-3);
    });
  }
  function fullRedraw(hi){
    ctx.clearRect(0,0,W,H);drawBase();
    if(hi!=null){ctx.save();ctx.strokeStyle="rgba(255,255,255,.08)";ctx.lineWidth=1;ctx.setLineDash([3,5]);ctx.beginPath();ctx.moveTo(PAD_L+hi*step,PAD_T);ctx.lineTo(PAD_L+hi*step,baseline);ctx.stroke();ctx.setLineDash([]);ctx.restore();}
    drawChannels(hi);drawLabels();
  }
  fullRedraw(null);
  canvas.onmousemove=function(e){
    const rect=canvas.getBoundingClientRect();
    const mx=(e.clientX-rect.left)*(W/rect.width);
    const idx=Math.min(N-1,Math.max(0,Math.round((mx-PAD_L)/step)));
    const r=pts_runs[idx];if(!r){tooltip.style.display="none";return;}
    const time=new Date(r.started_ts*1000).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
    const dur=r.duration_ms!=null?r.duration_ms+"ms":"—";
    const rows=CHANNELS.map(ch=>"<span style='color:"+ch.color+"'>&#9679;</span> "+ch.label+": <b>"+(r[ch.key]||0)+"</b>").join("<br>");
    const errRow=r.error_text?"<br><span style='color:var(--red)'>&#9888; "+esc(r.error_text.slice(0,60))+"</span>":"";
    tooltip.style.display="block";tooltip.style.left=Math.min(W-80,Math.max(40,PAD_L+idx*step))+"px";tooltip.style.top="4px";tooltip.style.transform="translateX(-50%)";
    tooltip.innerHTML="<div style='font-size:10px;color:var(--muted);margin-bottom:3px'>"+time+" &nbsp;·&nbsp; "+dur+"</div>"+rows+errRow;
    fullRedraw(idx);
  };
  canvas.onmouseleave=function(){tooltip.style.display="none";fullRedraw(null);};
  const totals=CHANNELS.map(ch=>{const sum=pts_runs.reduce((a,r)=>a+(r[ch.key]||0),0);return "<span style='color:"+ch.color+"'>&#9679; "+ch.label+"</span> <b>"+sum+"</b>";}).join(" &nbsp;·&nbsp; ");
  stats.innerHTML="<span style='color:var(--muted)'>"+N+" passes</span>&nbsp;&nbsp;"+totals;
}

// ── GRAPH ──
function initSalienceSlider(status){
  if(window.salienceSliderInitialized)return;
  const maxSal=Number(status?.schema_health?.active_salience?.max||25);
  const upper=Math.max(1,Math.ceil(maxSal));
  const minEl=document.getElementById("graphMinSalience");
  if(!minEl)return;
  minEl.max=String(upper);
  document.getElementById("graphObservedMaxSalienceLabel").textContent=maxSal.toFixed(2);
  window.salienceSliderInitialized=true;
  syncSalienceSlider(false);
}
function syncSalienceSlider(autoLoad=true){
  const minEl=document.getElementById("graphMinSalience");
  const min=Number(minEl.value);
  document.getElementById("graphMinSalienceLabel").textContent=min.toFixed(2);
  clearTimeout(window.salienceLoadTimer);
  if(autoLoad)window.salienceLoadTimer=setTimeout(loadGraph,400);
}
function resetSalienceSlider(){
  document.getElementById("graphMinSalience").value="0";
  syncSalienceSlider();
}
async function loadGraph(){
  const sts=[...document.querySelectorAll(".gstat:checked")].map(x=>x.value).join(",");
  const lim=document.getElementById("graphLimit").value;
  const scope=encodeURIComponent(document.getElementById("graphScope").value);
  const minSal=encodeURIComponent(document.getElementById("graphMinSalience").value);
  const d=await getJSON(`/api/graph/schemas?limit=${lim}&statuses=${sts}&scope=${scope}&min_salience=${minSal}`);
  renderLegend();
  drawGraph(d);
}
function renderLegend(){
  const el=document.getElementById("graphLegend");
  if(!el)return;
  const statusEntries=Object.entries(statusColor).map(([k,v])=>`<div class="legend-item"><div class="legend-dot" style="background:${v}"></div>${k}</div>`).join("");
  const relEntries=Object.entries(relColor).map(([k,v])=>`<div class="legend-item"><div class="legend-line" style="background:${v}"></div>${relLabel[k]||k}</div>`).join("");
  document.getElementById("graphLegend").innerHTML=`
    <div style="font-size:11px;color:var(--muted);font-weight:600;margin-right:4px">Nodes:</div>${statusEntries}
    <div style="width:1px;background:var(--line);margin:0 6px"></div>
    <div style="font-size:11px;color:var(--muted);font-weight:600;margin-right:4px">Edges:</div>${relEntries}
  `;
}
let schemaCy=null;
let graphLabelsForced=false;
function effectiveNodeStatus(n){return n.needs_review?"needs_review":(n.status||"active");}
function nodeColor(n){return statusColor[effectiveNodeStatus(n)]||"#5a6e91";}
function graphNodeSize(n){return 12+Math.min(34,Math.sqrt(Math.max(0,Number(n.salience||0)))*3.2);}
function graphNodeLabel(n){return `sch_${n.schema_id}`;}
function updateGraphLabels(){
  if(!schemaCy)return;
  const show=graphLabelsForced||schemaCy.zoom()>0.85||schemaCy.nodes().length<=80;
  schemaCy.nodes().forEach(n=>{
    n.style("label",show?n.data("label"):"");
  });
}
function fitGraph(){if(schemaCy){schemaCy.fit(undefined,40);updateGraphLabels();}}
function toggleGraphLabels(){graphLabelsForced=!graphLabelsForced;updateGraphLabels();}
function randomPointInDisk(radius){
  const r=radius*Math.sqrt(Math.random()),a=Math.random()*2*Math.PI;
  return {x:r*Math.cos(a),y:r*Math.sin(a)};
}
function rerunGraphLayout(){
  if(!schemaCy)return;
  schemaCy.layout({name:"cose",animate:true,animationDuration:400,fit:true,padding:50,gravity:0,numIter:150}).run();
}
function drawGraph(g){
  const cyEl=document.getElementById("schemaGraphCy");
  const svg=document.getElementById("schemaGraph");
  const meta=document.getElementById("graphMeta");
  const nodes=g.nodes||[],edges=g.edges||[];
  if(meta)meta.textContent=`${nodes.length} schemas · ${edges.length} relations · limit ${g.limit}`;
  if(!window.cytoscape){
    if(cyEl)cyEl.innerHTML=`<div class="graph-empty">Cytoscape failed to load; using SVG fallback.</div>`;
    if(svg)svg.style.display="block";
    drawGraphSvgFallback(g);
    return;
  }
  if(svg)svg.style.display="none";
  if(!nodes.length){
    if(schemaCy){schemaCy.destroy();schemaCy=null;}
    cyEl.innerHTML=`<div class="graph-empty">No nodes for selected filters</div>`;
    return;
  }
  cyEl.innerHTML="";
  if(schemaCy){schemaCy.destroy();schemaCy=null;}
  const elements=[];
  nodes.forEach(n=>{
    const stage=Number(n.generalization_stage||0);
    elements.push({data:{
      id:n.id,label:graphNodeLabel(n),schema_id:n.schema_id,content:n.content||n.label||"",
      status:n.status,effective_status:effectiveNodeStatus(n),scope:n.scope||"",schema_class:n.schema_class||"",
      salience:Number(n.salience||0),confidence:Number(n.confidence||0),stage,needs_review:!!n.needs_review,
      color:nodeColor(n),size:graphNodeSize(n),border:stage>=3?"#6af5aa":stage===2?"#ffd580":stage===1?"#7ab5ff":"#253050",
      borderWidth:n.needs_review?4:(stage>0?2.5:1.2)
    },position:randomPointInDisk(1600)});
  });
  edges.forEach(e=>{
    elements.push({data:{
      id:e.id,source:e.source,target:e.target,relation:e.relation,confidence:Number(e.confidence||0.5),
      color:relColor[e.relation]||"#5a6e91",width:1+3*Number(e.confidence||0.5),
      label:relLabel[e.relation]||e.relation,reason:e.reason||"",src_schema_id:e.src_schema_id,dst_schema_id:e.dst_schema_id
    }});
  });
  schemaCy=cytoscape({
    container:cyEl,
    elements,
    minZoom:0.08,
    maxZoom:3.0,
    layout:{name:"preset",fit:true,padding:50},
    style:[
      {selector:"node",style:{
        "background-color":"data(color)","width":"data(size)","height":"data(size)",
        "border-color":"data(border)","border-width":"data(borderWidth)","border-opacity":0.95,
        "label":"","color":"#b8c8e8","font-size":10,"text-outline-color":"#050b18","text-outline-width":2,
        "text-valign":"bottom","text-halign":"right","text-margin-x":4,"text-margin-y":4,
        "overlay-padding":6,"transition-property":"border-width, opacity","transition-duration":"120ms"
      }},
      {selector:"node[effective_status = 'superseded']",style:{"opacity":0.55}},
      {selector:"node[effective_status = 'archived']",style:{"opacity":0.38}},
      {selector:"edge",style:{
        "line-color":"data(color)","target-arrow-color":"data(color)","target-arrow-shape":"triangle",
        "width":"data(width)","curve-style":"bezier","opacity":0.48,
        "label":"","font-size":8,"color":"data(color)","text-background-color":"#050b18","text-background-opacity":0.75,"text-background-padding":2
      }},
      {selector:"node:selected",style:{"border-color":"#fff","border-width":5,"z-index":20}},
      {selector:".faded",style:{"opacity":0.12}},
      {selector:".highlight",style:{"opacity":1,"z-index":30}},
      {selector:"edge.highlight",style:{"opacity":0.95,"width":4}}
    ]
  });
  // Gentle cose pass: pull connected nodes together while isolated ones stay scattered
  // PENDING EVAL - current test shows cose re-converges even at low iterations; disabled for now.
  // Use "Layout" button to run cose and see if edge clustering helps.
  schemaCy.on("zoom",updateGraphLabels);
  schemaCy.on("mouseover","node",ev=>{
    const n=ev.target.data();
    showTip(ev.originalEvent,`<b>${esc(n.label)}</b><br><span style="color:#7a8db5">${esc(n.effective_status)}</span> · sal ${Number(n.salience).toFixed(3)} · stage ${n.stage}<br><em>${esc(String(n.content||"").slice(0,180))}</em>`);
  });
  schemaCy.on("mouseout","node",hideTip);
  schemaCy.on("mouseover","edge",ev=>{
    const e=ev.target.data();
    showTip(ev.originalEvent,`<b>${esc(e.relation)}</b><br>sch_${e.src_schema_id} → sch_${e.dst_schema_id}<br>confidence: ${Number(e.confidence||0).toFixed(2)}${e.reason?`<br><em>${esc(e.reason)}</em>`:""}`);
  });
  schemaCy.on("mouseout","edge",hideTip);
  schemaCy.on("tap","node",ev=>{
    const node=ev.target;
    schemaCy.elements().removeClass("faded highlight");
    const neighborhood=node.closedNeighborhood();
    schemaCy.elements().not(neighborhood).addClass("faded");
    neighborhood.addClass("highlight");
    selectGraphNode(node.data(),null);
    updateGraphLabels();
  });
  schemaCy.on("tap",ev=>{
    if(ev.target===schemaCy){schemaCy.elements().removeClass("faded highlight");updateGraphLabels();}
  });
  updateGraphLabels();
}
function drawGraphSvgFallback(g){
  const svg=document.getElementById("schemaGraph");
  svg.innerHTML=`<defs>
    <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L8,3 z" fill="#7a8db5" opacity="0.8"/>
    </marker>
    <filter id="glow"><feGaussianBlur stdDeviation="2" result="coloredBlur"/>
      <feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>`;
  const w=svg.clientWidth||900,h=svg.clientHeight||660,cx=w/2,cy=h/2;
  const nodes=g.nodes||[],edges=g.edges||[];
  if(!nodes.length){
    const t=document.createElementNS("http://www.w3.org/2000/svg","text");
    t.setAttribute("x",cx);t.setAttribute("y",cy);
    t.setAttribute("text-anchor","middle");t.setAttribute("fill","#5a6e91");t.setAttribute("font-size","14");
    t.textContent="No nodes for selected filters";
    svg.appendChild(t);return;
  }
  const byId=Object.fromEntries(nodes.map(n=>[n.id,n]));
  // Initial layout: spiral
  nodes.forEach((n,i)=>{
    const a=2*Math.PI*i/Math.max(1,nodes.length);
    const r=Math.min(w,h)*(0.25+0.2*((i%5)/5));
    n.x=cx+Math.cos(a)*r;n.y=cy+Math.sin(a)*r;
    n.vx=0;n.vy=0;
  });
  // Force-directed layout
  for(let iter=0;iter<120;iter++){
    nodes.forEach(n=>{n.vx*=0.78;n.vy*=0.78;});
    for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
      const a=nodes[i],b=nodes[j],dx=a.x-b.x,dy=a.y-b.y;
      const d2=dx*dx+dy*dy+0.01,d=Math.sqrt(d2),force=1100/d2;
      a.vx+=dx/d*force;b.vx-=dx/d*force;
      a.vy+=dy/d*force;b.vy-=dy/d*force;
    }
    edges.forEach(e=>{
      const a=byId[e.source],b=byId[e.target];
      if(!a||!b)return;
      const dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)+0.01,force=(d-160)*0.003;
      a.vx+=dx/d*force;b.vx-=dx/d*force;
      a.vy+=dy/d*force;b.vy-=dy/d*force;
    });
    // center gravity
    nodes.forEach(n=>{
      n.vx+=(cx-n.x)*0.002;n.vy+=(cy-n.y)*0.002;
      n.x=Math.max(24,Math.min(w-24,n.x+n.vx));
      n.y=Math.max(24,Math.min(h-24,n.y+n.vy));
    });
  }
  // Draw edges
  edges.forEach(e=>{
    const a=byId[e.source],b=byId[e.target];
    if(!a||!b)return;
    const color=relColor[e.relation]||"#5a6e91";
    const sw=1.5+2*(e.confidence||0.5);
    // offset for arrow
    const dx=b.x-a.x,dy=b.y-a.y,d=Math.sqrt(dx*dx+dy*dy)+0.01;
    const x2=b.x-dx/d*12,y2=b.y-dy/d*12;
    const line=document.createElementNS("http://www.w3.org/2000/svg","line");
    line.setAttribute("x1",a.x);line.setAttribute("y1",a.y);
    line.setAttribute("x2",x2);line.setAttribute("y2",y2);
    line.setAttribute("class","edge");line.setAttribute("stroke",color);
    line.setAttribute("stroke-width",sw);line.setAttribute("marker-end","url(#arrow)");
    line.addEventListener("mouseenter",ev=>showTip(ev,`<b>${e.relation}</b><br>sch_${e.src_schema_id} → sch_${e.dst_schema_id}<br>confidence: ${Number(e.confidence||0).toFixed(2)}${e.reason?`<br><em>${esc(e.reason)}</em>`:""}`) );
    line.addEventListener("mouseleave",hideTip);
    svg.appendChild(line);
    // edge label mid-point
    const t=document.createElementNS("http://www.w3.org/2000/svg","text");
    t.setAttribute("x",(a.x+b.x)/2);t.setAttribute("y",(a.y+b.y)/2-3);
    t.setAttribute("class","edge-label");t.setAttribute("text-anchor","middle");
    t.setAttribute("fill",color);t.textContent=relLabel[e.relation]||e.relation;
    svg.appendChild(t);
  });
  // Draw nodes
  nodes.forEach(n=>{
    const r=8+Math.min(18,Math.sqrt(Math.max(0,n.salience))*3.5);
    const color=statusColor[n.status]||"#5a6e91";
    const c=document.createElementNS("http://www.w3.org/2000/svg","circle");
    c.setAttribute("cx",n.x);c.setAttribute("cy",n.y);c.setAttribute("r",r);
    c.setAttribute("fill",color);c.setAttribute("fill-opacity","0.85");
    c.setAttribute("stroke",color);c.setAttribute("stroke-width","1.5");
    c.setAttribute("class","node");
    c.addEventListener("mouseenter",ev=>showTip(ev,`<b>sch_${n.schema_id}</b><br><span style="color:#7a8db5">${esc(n.status)}</span> · sal ${Number(n.salience).toFixed(3)}<br><em>${esc(n.label)}</em>`));
    c.addEventListener("mouseleave",hideTip);
    c.onclick=()=>selectGraphNode(n,c);
    svg.appendChild(c);
    // short label
    const lab=document.createElementNS("http://www.w3.org/2000/svg","text");
    lab.setAttribute("x",n.x+r+3);lab.setAttribute("y",n.y+4);
    lab.setAttribute("class","node-label");lab.textContent=`sch_${n.schema_id}`;
    svg.appendChild(lab);
  });
}
async function selectGraphNode(n,el){
  if(el){document.querySelectorAll(".node").forEach(x=>x.classList.remove("selected"));el.classList.add("selected");}
  const d=await getJSON(`/api/schemas/${n.schema_id}`);
  const s=d.schema||n;
  const eStat=effectiveNodeStatus(s);
  const evHtml=d.evidence&&d.evidence.length
    ?table(["Ep.","Evt.","Weight","Quote"],d.evidence.map(e=>[
        e.episode_id?`epi_${e.episode_id}`:"—",e.raw_event_id?`evt_${e.raw_event_id}`:"—",
        Number(e.weight||0).toFixed(3),e.quote||"—"]))
    :"<em style='color:var(--muted)'>No evidence.</em>";
  const outHtml=d.outgoing&&d.outgoing.length
    ?table(["To","Rel.","Conf.","Reason"],d.outgoing.map(e=>[
        `sch_${e.dst_schema_id}`,e.relation,Number(e.confidence||0).toFixed(2),e.reason||"—"]))
    :"<em style='color:var(--muted)'>None.</em>";
  const inHtml=d.incoming&&d.incoming.length
    ?table(["From","Rel.","Conf.","Reason"],d.incoming.map(e=>[
        `sch_${e.src_schema_id}`,e.relation,Number(e.confidence||0).toFixed(2),e.reason||"—"]))
    :"<em style='color:var(--muted)'>None.</em>";
  document.getElementById("graphDetail").innerHTML=`
    <div style="margin-bottom:10px">
      <div style="font-size:16px;font-weight:700">sch_${s.schema_id}</div>
      <div style="margin-top:6px">${pill(eStat)}
        <span class="pill">sal ${Number(s.salience).toFixed(3)}</span>
        <span class="pill">conf ${Number(s.confidence).toFixed(2)}</span>
        ${s.schema_class?`<span class="pill">${esc(s.schema_class)}</span>`:""}
        ${s.needs_review?`<span class="pill pill-warn">⚠ review</span>`:""}
      </div>
    </div>
    <div style="font-size:13px;color:var(--text);line-height:1.6;margin-bottom:12px;padding:10px;background:var(--panel2);border-radius:var(--radius-sm);border:1px solid var(--line)">${esc(s.content)}</div>
    <div class="detail-section"><h4>Facets</h4><pre class="code-block">${esc(JSON.stringify(s.facets,null,2))}</pre></div>
    <div class="detail-section"><h4>Tags</h4>${(s.tags||[]).map(t=>`<span class="pill">${esc(t)}</span>`).join("")||"<em style='color:var(--muted)'>none</em>"}</div>
    <div class="detail-section"><h4>Outgoing relations</h4>${outHtml}</div>
    <div class="detail-section"><h4>Incoming relations</h4>${inHtml}</div>
    <div class="detail-section"><h4>Evidence</h4>${evHtml}</div>
    <div style="margin-top:10px;font-size:11px;color:var(--muted)">First formed: ${fmtTs(s.first_formed_ts)}<br>Last updated: ${fmtTs(s.last_updated_ts)}</div>
  `;
}

// ── RECALL ──
async function runRecall(){
  const query=document.getElementById("recallQuery").value.trim();
  if(!query)return;
  const top_k=parseInt(document.getElementById("recallTopK").value)||5;
  const evidence=document.getElementById("recallEvidence").checked;
  const ld=document.getElementById("recallLoading");
  const res=document.getElementById("recallResults");
  ld.classList.add("show");res.innerHTML="";
  try{
    const d=await postJSON("/api/recall",{query,top_k,evidence});
    if(d.error){
      res.innerHTML=`<div class="alert alert-error"><span class="alert-icon">❌</span><div><b>Error</b><br>${esc(d.error)}</div></div>`;
      return;
    }
    const maxSal=Math.max(1,...(d.schemas||[]).map(s=>s.salience||0));
    let html="";
    if(d.schemas&&d.schemas.length){
      html+=`<div style="font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin:14px 0 6px">📖 Schemas (${d.schemas.length})</div>`;
      html+=table(
        ["ID","Status","Salience","Class","Content"],
        d.schemas.map(s=>[
          `<code style="font-size:11px">sch_${s.id||s.schema_id}</code>`,
          pill(s.status),
          salBar(s.salience||0,maxSal)+` <span style="font-size:11px">${Number(s.salience||0).toFixed(3)}</span>`,
          esc(s.facets?.schema_class||s.schema_class||"—"),
          esc(s.content_text||s.content||"")
        ]),
        [0,1,2]
      );
    }
    if(d.episodes&&d.episodes.length){
      html+=`<div style="font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin:14px 0 6px">🎞 Episodes (${d.episodes.length})</div>`;
      html+=table(
        ["ID","Salience","Date","Content"],
        d.episodes.map(e=>[
          `epi_${e.id}`,
          Number(e.salience||0).toFixed(3),
          fmtDate(e.ts||0),
          esc((e.content_text||"").slice(0,200))
        ]),
        [0]
      );
    }
    if(d.raw_events&&d.raw_events.length){
      html+=`<div style="font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin:14px 0 6px">🗒 Evidence events (${d.raw_events.length})</div>`;
      html+=table(
        ["ID","Type","Content"],
        d.raw_events.map(e=>[`evt_${e.id}`,e.type||"—",esc((e.content_preview||"").slice(0,200))]),
        [0]
      );
    }
    if(!html)html=emptyState("No results for this query.","🔍");
    res.innerHTML=html;
  }finally{ld.classList.remove("show");}
}
// Enter key in recall textarea
document.getElementById("recallQuery").addEventListener("keydown",e=>{
  if(e.key==="Enter"&&(e.metaKey||e.ctrlKey))runRecall();
});

// ── DB HEALTH ──
async function loadDbHealth(){
  const ld=document.getElementById("dbHealthLoading");
  const el=document.getElementById("dbHealth");
  ld.classList.add("show");el.innerHTML="";
  try{
    const d=await getJSON("/api/db/health");
    if(!d.db_exists){
      el.innerHTML=`<div class="alert alert-error"><span class="alert-icon">❌</span><div>Database not found at <code>${esc(d.db_path)}</code></div></div>`;
      return;
    }
    const integrityOk=d.integrity_check&&d.integrity_check.length===1&&d.integrity_check[0]==="ok";
    const fkOk=!d.foreign_key_check||d.foreign_key_check.length===0;
    let html=`
      <div class="two-col" style="margin-bottom:12px">
        <div class="panel">
          <div class="panel-title">Pragmas</div>
          <pre class="code-block">${esc(JSON.stringify(d.pragmas,null,2))}</pre>
        </div>
        <div class="panel">
          <div class="panel-title">Integrity</div>
          <div class="alert ${integrityOk?"alert-ok":"alert-error"}">
            <span class="alert-icon">${integrityOk?"✅":"❌"}</span>
            <div>${integrityOk?"Integrity check passed":`Issues: ${esc(JSON.stringify(d.integrity_check))}`}</div>
          </div>
          <div class="alert ${fkOk?"alert-ok":"alert-warn"}" style="margin-top:8px">
            <span class="alert-icon">${fkOk?"✅":"⚠️"}</span>
            <div>${fkOk?"No FK violations":"FK violations: "+esc(JSON.stringify(d.foreign_key_check))}</div>
          </div>
        </div>
      </div>
    `;
    html+=`<div class="panel"><div class="panel-title">Tables &amp; Views</div>`;
    html+=table(
      ["Name","Type","Row count"],
      (d.tables||[]).map(t=>[t.name,t.type,t.count!=null?num(t.count):"—"])
    );
    html+="</div>";
    el.innerHTML=html;
  }finally{ld.classList.remove("show");}
}
// ── SESSION REPLAY ──
async function loadSessionTimeline(sid){
  let detail=document.getElementById("sessionTimeline");
  if(!detail){
    detail=document.createElement("div");
    detail.id="sessionTimeline";
    detail.style.cssText="margin-top:10px;padding:12px;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);max-height:500px;overflow-y:auto;display:none";
    const sessPanel=document.getElementById("recentSessions");
    if(sessPanel)sessPanel.parentNode.appendChild(detail);
  }
  detail.innerHTML=`<div style=\"text-align:center;padding:12px;color:var(--muted)\">Loading timeline…</div>`;
  detail.style.display="block";
  try{
    const d=await getJSON(`/api/sessions/${encodeURIComponent(sid)}/timeline`);
    if(d.error){detail.innerHTML=emptyState(d.error,"⚠️");return;}
    const sess=d.session;
    let html=`<div style=\"background:var(--panel2);border:1px solid var(--line);padding:12px;margin-bottom:10px\">`;
    html+=`<div style=\"display:flex;justify-content:space-between;align-items:center\">`;
    html+=`<div><b>Session ${esc(sess.id).slice(0,16)}…</b></div>`;
    html+=`<button class=\"btn\" style=\"font-size:11px;padding:2px 8px\" onclick=\"document.getElementById('sessionTimeline').style.display='none'\">✕ Close</button></div>`;
    html+=`<div style=\"font-size:12px;color:var(--muted);margin-top:4px\">Agent: ${esc(sess.agent)} · Scope: ${esc(sess.scope_id||"—")} · Goal: ${esc(sess.goal||"—")}</div>`;
    html+=`<div style=\"font-size:11px;color:var(--muted)\">${fmtTs(sess.started_ts)} → ${sess.ended_ts?fmtTs(sess.ended_ts):"ongoing"} · Outcome: ${esc(sess.outcome||"—")}</div></div>`;
    const events=d.events||[];
    if(!events.length){
      html+=emptyState("No events in this session.","📭");
    } else {
      html+=`<div style=\"position:relative;padding-left:20px;border-left:2px solid var(--line2)\">`;
      events.forEach(ev=>{
        const icon=ev.type==="user_message"?"👤":ev.type==="assistant_message"?"🤖":ev.type==="activate"?"▶️":"📌";
        html+=`<div style=\"margin-bottom:10px;position:relative\">`;
        html+=`<span style=\"position:absolute;left:-29px;top:2px;font-size:14px\">${icon}</span>`;
        html+=`<div style=\"font-size:10px;color:var(--muted);margin-bottom:2px\">${fmtTsCompact(ev.ts)} · <span class=\"pill\" style=\"font-size:9px;padding:1px 4px\">${esc(ev.type)}</span></div>`;
        html+=`<div style=\"font-size:12px;line-height:1.4\">${truncContent(ev.content||"",300)}</div></div>`;
      });
      html+=`</div>`;
    }
    detail.innerHTML=html;detail.scrollIntoView({behavior:"smooth"});
  }catch(e){detail.innerHTML=emptyState("Error: "+esc(String(e)),"⚠️");}
}

// ── SUPERSESSIONS ──
async function loadSupersessions(){
  const ld=document.getElementById("supersessionLoading");
  const el=document.getElementById("supersessionTable");
  ld.classList.add("show");el.innerHTML="";
  try{
    const d=await getJSON("/api/supersessions?limit=100");
    if(!d.supersessions||!d.supersessions.length){el.innerHTML=emptyState("No supersessions found.","🔄");return;}
    const rows=d.supersessions.map(s=>[
      `<code style=\"color:var(--purple)\">sch_${s.src_schema_id}</code>`,
      `<code style=\"color:var(--green)\">sch_${s.dst_schema_id}</code>`,
      confBar(s.confidence),
      `<div style=\"max-width:240px\">${esc((s.reason||"n/a").slice(0,60))}${(s.reason||"").length>60?"…":""}</div>`,
      `<div style=\"font-size:11px\">${esc((s.src_content||"").slice(0,80))}…<br><span style=\"color:var(--purple);font-size:10px\">${esc(s.src_status)}</span></div>`,
      `<div style=\"font-size:11px\">${esc((s.dst_content||"").slice(0,80))}…<br><span style=\"color:var(--green);font-size:10px\">${esc(s.dst_status)}</span></div>`,
      fmtTsCompact(s.created_ts)
    ]);
    el.innerHTML=`<div style=\"font-size:11px;color:var(--muted);margin-bottom:6px\">${num(d.total)} supersession chains</div>`
      +table(["Old","New","Confidence","Reason","Old content","New content","When"],rows,[0,1,3,4,5]);
  }finally{ld.classList.remove("show");}
}
// ── SALIENCE HISTOGRAM ──
function renderSalienceHistogram(){
  const d=window.lastStatus;
  if(!d||!d.schema_health)return;
  const canvas=document.getElementById("salienceHistCanvas");
  if(!canvas)return;
  const ctx=canvas.getContext("2d");
  const W=canvas.clientWidth,H=canvas.height;
  canvas.width=W;canvas.height=H;
  const pad={top:10,right:16,bottom:22,left:40};
  const pw=W-pad.left-pad.right,ph=H-pad.top-pad.bottom;
  const sal=d.schema_health.active_salience||{};
  const minS=Number(sal.min||0),maxS=Math.max(0.001,Number(sal.max||10));
  const avgS=Number(sal.avg||0);
  ctx.clearRect(0,0,W,H);
  ctx.fillStyle="#080e1c";ctx.fillRect(0,0,W,H);
  if(maxS<=0){ctx.fillStyle="#5a6e91";ctx.font="12px Inter,sans-serif";ctx.textAlign="center";ctx.fillText("No salience data",W/2,H/2);return;}
  const bins=20;const binW=pw/bins;
  const spread=Math.max(0.01,(maxS-minS)/4);
  const vals=[];
  for(let i=0;i<bins;i++){
    const x=minS+((i+0.5)/bins)*(maxS-minS);
    const z=(x-avgS)/spread;vals.push(Math.exp(-0.5*z*z));
  }
  const maxV=Math.max(0.01,...vals);
  const colors=["#3ecf6e","#4f9bff","#f5b942","#9d71f0","#f04e6a"];
  ctx.strokeStyle="#1e2d4a";ctx.lineWidth=1;
  for(let i=0;i<bins;i++){
    const h=(vals[i]/maxV)*ph;
    ctx.fillStyle=colors[i%5]+"88";
    ctx.fillRect(pad.left+i*binW,pad.top+ph-h,binW-1,h);
    ctx.strokeRect(pad.left+i*binW,pad.top+ph-h,binW-1,h);
  }
  ctx.strokeStyle="#2a3d5a";ctx.lineWidth=1;
  ctx.beginPath();ctx.moveTo(pad.left,pad.top);ctx.lineTo(pad.left,pad.top+ph);ctx.lineTo(pad.left+pw,pad.top+ph);ctx.stroke();
  ctx.fillStyle="#5a6e91";ctx.font="10px Inter,sans-serif";ctx.textAlign="right";
  for(let i=0;i<=3;i++){
    const y=pad.top+ph-(i/3)*ph;
    ctx.fillText(i===0?"0":(i/3).toFixed(1),pad.left-6,y+3);
  }
  ctx.textAlign="center";
  for(let i=0;i<=4;i++){
    const x=pad.left+(i/4)*pw;
    ctx.fillText((minS+(i/4)*(maxS-minS)).toFixed(2),x,pad.top+ph+14);
  }
  // min/avg/max markers
  ctx.setLineDash([3,4]);ctx.strokeStyle="#5a6e91";
  [minS,avgS,maxS].forEach(v=>{
    const x=pad.left+((v-minS)/(maxS-minS||1))*pw;
    ctx.beginPath();ctx.moveTo(x,pad.top);ctx.lineTo(x,pad.top+ph);ctx.stroke();
  });
  ctx.setLineDash([]);ctx.fillStyle="#7a8db5";ctx.font="bold 10px Inter,sans-serif";
  ctx.fillText("min",pad.left+((minS-minS)/(maxS-minS||1))*pw+8,pad.top+12);
  ctx.fillText("avg",pad.left+((avgS-minS)/(maxS-minS||1))*pw,pad.top-2);
  ctx.fillText("max",pad.left+((maxS-minS)/(maxS-minS||1))*pw-8,pad.top+12);
}

// ── GENERALIZATION ──
const GEN_LABELS=['SCOPED','PORTABLE','CONTEXTUAL','GLOBAL'];
const GEN_COLORS=['var(--gray)','var(--blue)','var(--amber)','var(--green)'];
const GEN_DESC=[
  'Only retrieved within its origin scope',
  'Retrieved across same-kind scopes (e.g. project:* → project:*)',
  'Retrieved everywhere with a relevance floor',
  'Retrieved everywhere with no restriction',
];
function genBadge(stage){
  const lbl=GEN_LABELS[stage]||'SCOPED';
  return `<span class="gen-badge gen-${stage}">${lbl}</span>`;
}
function genBreadthBar(pct,label,color,count){
  const w=Math.round(Math.min(100,pct*100));
  const detail=count!=null?` · ${count}`:'';
  const fill=color||'var(--blue)';
  return `<div class="gen-bar-wrap">
    <div class="gen-bar-track"><div class="gen-bar" style="width:${w}%;background:${fill}"></div></div>
    <span style="font-size:11px;color:var(--muted);white-space:nowrap">${label}: ${(pct*100).toFixed(0)}%${detail}</span>
  </div>`;
}
async function loadGeneralization(){
  const ld=document.getElementById("genLoading");
  ld.classList.add("show");
  try{
    const d=await getJSON("/api/generalization");
    const sum=d.summary||{};
    const dist=d.stage_distribution||{};
    // Stat cards
    const cards=[
      {icon:"📖",label:"Total active",val:num(sum.total_active_schemas),accent:"var(--green)"},
      {icon:"🚀",label:"Portable",val:num(dist[1]||0),sub:"stage 1",accent:"var(--blue)"},
      {icon:"🌍",label:"Contextual",val:num(dist[2]||0),sub:"stage 2",accent:"var(--amber)"},
      {icon:"✨",label:"Global",val:num(dist[3]||0),sub:"stage 3",accent:"var(--green)"},
      {icon:"🗺",label:"Known scopes",val:num(sum.total_known_scopes),sub:num(sum.total_scope_kinds)+" kinds",accent:"var(--cyan)"},
    ];
    document.getElementById("genStatGrid").innerHTML=cards.map(c=>
      `<div class="stat-card" style="--accent:${c.accent}">
        <div class="sc-icon">${c.icon}</div>
        <div class="sc-label">${esc(c.label)}</div>
        <div class="sc-value">${esc(String(c.val))}</div>
        <div class="sc-sub">${esc(c.sub||"")}</div>
      </div>`
    ).join("");
    // Stage distribution visual
    const totalActive=Math.max(1,sum.total_active_schemas);
    let distHtml='<div style="margin-bottom:14px">';
    [0,1,2,3].forEach(st=>{
      const n=dist[st]||0;const pct=Math.round(n/totalActive*100);
      distHtml+=`<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        ${genBadge(st)}
        <div class="gen-bar-track" style="flex:1"><div class="gen-bar" style="width:${pct}%;background:${GEN_COLORS[st]}"></div></div>
        <span style="font-size:12px;color:var(--muted);width:40px;text-align:right">${num(n)}</span>
      </div>`;
    });
    distHtml+='</div>';
    // Promoted list
    const items=d.top_promoted||[];
    if(!items.length){
      document.getElementById("genPromotedList").innerHTML=distHtml+emptyState("No promoted memories yet. Memories promote as they are recalled across multiple scopes.","🌐");
    } else {
      let listHtml=distHtml;
      items.forEach(m=>{
        listHtml+=`<div style="background:var(--panel2);border:1px solid var(--line);border-radius:var(--radius-sm);padding:10px 14px;margin-bottom:8px">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            ${genBadge(m.stage)}
            <code style="font-size:11px;color:var(--muted)">${esc(m.id)}</code>
            <span style="font-size:11px;color:var(--muted)">origin: ${esc(m.scope||"—")}</span>
          </div>
          <div style="font-size:13px;line-height:1.5;margin-bottom:8px">${esc(m.content)}</div>
          ${genBreadthBar(m.scope_breadth_pct||0,"scope breadth","var(--blue)",m.distinct_scope_count+" scope"+(m.distinct_scope_count!==1?"s":""))}
          ${genBreadthBar(m.scope_kind_breadth_pct||0,"kind breadth","var(--amber)",m.distinct_scope_kind_count+" kind"+(m.distinct_scope_kind_count!==1?"s":""))}
          <div style="font-size:11px;color:var(--muted);margin-top:4px">
            ${m.distinct_scope_count} scope${m.distinct_scope_count!==1?"s":""} · 
            ${m.distinct_scope_kind_count} kind${m.distinct_scope_kind_count!==1?"s":""} · 
            ${m.cross_scope_recall_count} cross-scope recall${m.cross_scope_recall_count!==1?"s":""}
          </div>
        </div>`;
      });
      document.getElementById("genPromotedList").innerHTML=listHtml;
    }
    // Scope registry
    const reg=d.scope_registry||[];
    if(!reg.length){
      document.getElementById("genScopeRegistry").innerHTML=emptyState("No scopes registered yet. Scopes are recorded automatically when sessions start.","🗺");
    } else {
      document.getElementById("genScopeRegistry").innerHTML=reg.map(r=>`
        <div class="scope-reg-card">
          <div>
            <div class="scope-reg-id">${esc(r.scope_id)}</div>
            <div class="scope-reg-meta">${r.scope_kind||"generic"} · last active ${fmtDate(r.last_active_ts)}</div>
          </div>
          <div style="text-align:right;font-size:12px;color:var(--muted)">
            <div>${num(r.session_count)} session${r.session_count!==1?"s":""}</div>
            <div>${num(r.recall_count)} recall${r.recall_count!==1?"s":""}</div>
          </div>
        </div>`).join("");
    }
  }finally{ld.classList.remove("show");}
}

// ── INIT ──
// Ensure new functions are globally accessible
window.loadSessionTimeline = loadSessionTimeline;
window.loadSupersessions = loadSupersessions;

loadStatus();
renderPulse();
setInterval(loadStatus,REFRESH_MS);
setInterval(renderPulse,REFRESH_MS);
'''
