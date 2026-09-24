"""Read-first localhost console over control-plane DTOs, with no mutation routes."""

from __future__ import annotations

import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, cast

from .api import call
from .contracts import encode
from .plane import Plane

HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Agentic Discipline · Project Console</title><link rel="stylesheet" href="/app.css"></head><body><header><div><small>AGENTIC DISCIPLINE</small><h1 id="project">Project console</h1></div><button id="refresh">Refresh</button></header><main><p id="error" role="alert"></p><div id="metrics" class="metrics"></div><nav><a href="#assurance">Assurance</a><a href="#tasks">Execution</a><a href="#agents">Agents</a><a href="#evidence">Evidence</a><a href="#decisions">Decisions</a><a href="#knowledge">Knowledge</a></nav><section id="assurance"><h2>Assurance and proof debt</h2><div id="assuranceRows"></div></section><section id="obligations"><h2>Proof obligations</h2><div id="obligationRows"></div></section><section id="tasks"><h2>Execution</h2><div id="taskRows"></div></section><section id="agents"><h2>Agents and leases</h2><div id="agentRows"></div></section><section id="evidence"><h2>Evidence</h2><div id="evidenceRows"></div></section><section id="decisions"><h2>Decisions and conflicts</h2><div id="decisionRows"></div></section><section id="requirements"><h2>Requirements</h2><div id="requirementRows"></div></section><section id="evolution"><h2>Evolution and retired intent</h2><div id="evolutionRows"></div></section><section id="knowledge"><h2>Discovery coverage</h2><div id="coverageRows"></div></section><section><h2>Activity</h2><div id="activityRows"></div></section><p class="note">Current proof is checked against source files and verifier artifacts. Historical evidence remains available for audit.</p></main><script src="/app.js"></script></body></html>"""
CSS = """*{box-sizing:border-box}body{margin:0;background:#10151e;color:#e9edf5;font:15px system-ui,sans-serif}header,main{max-width:1150px;margin:auto;padding:30px}header{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #303b4d}small{letter-spacing:.17em;color:#72d6b8}h1{font-size:28px;margin:8px 0}h2{font-size:19px}button{border:1px solid #48617c;background:#1c2b3d;color:white;padding:10px 18px;border-radius:8px;cursor:pointer}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:14px}.metric,section{background:#18212f;border:1px solid #2c3a4e;border-radius:12px;padding:20px}.metric strong{display:block;font-size:30px;color:#72d6b8;margin-top:8px}section{margin:24px 0;overflow:auto}nav{display:flex;gap:24px;margin:28px 0;flex-wrap:wrap}a{color:#b9d6f3}table{width:100%;border-collapse:collapse}th,td{text-align:left;vertical-align:top;padding:12px 9px;border-bottom:1px solid #2d3a4c;max-width:460px;overflow-wrap:anywhere}th,.note{color:#a3b3c8}#error{color:#ffb5a8}.badge{font:12px ui-monospace,monospace}.empty{color:#a3b3c8}details{margin-top:6px}pre{white-space:pre-wrap;max-height:300px;overflow:auto}"""
JS = """const el=id=>document.getElementById(id);function table(id,headers,rows){const host=el(id);host.replaceChildren();if(!rows.length){const p=document.createElement('p');p.className='empty';p.textContent='No records yet';host.append(p);return;}const t=document.createElement('table'),head=t.createTHead().insertRow();headers.forEach(x=>{const h=document.createElement('th');h.textContent=x;head.append(h)});const b=t.createTBody();rows.forEach(row=>{const r=b.insertRow();row.forEach(value=>{const c=r.insertCell();if(typeof value==='object'){const d=document.createElement('details'),s=document.createElement('summary'),p=document.createElement('pre');s.textContent='Details';p.textContent=JSON.stringify(value,null,2);d.append(s,p);c.append(d)}else c.textContent=String(value??'—')})});host.append(t)}async function refresh(){try{el('error').textContent='';const response=await fetch('/api/status');if(!response.ok)throw Error('Project status unavailable');const s=(await response.json()).data;el('project').textContent=s.project.name;el('metrics').replaceChildren();[['Ready',s.task_counts.READY||0],['Running',(s.task_counts.CLAIMED||0)+(s.task_counts.RUNNING||0)+(s.task_counts.VERIFYING||0)],['Blocked',s.task_counts.BLOCKED||0],['Completed',s.task_counts.COMPLETED||0],['Stale evidence',s.evidence.filter(x=>x.stale).length],['Knowledge revision',s.knowledge_version]].forEach(([label,n])=>{const d=document.createElement('div'),v=document.createElement('strong');d.className='metric';d.textContent=label;v.textContent=n;d.append(v);el('metrics').append(d)});table('taskRows',['Task','State','Dependencies','Context'],s.tasks.map(t=>[t.objective,t.state,t.dependencies,t]));table('agentRows',['Agent','Capabilities','Lease'],s.agents.map(a=>[a.name,a.capabilities.join(', '),s.leases.filter(l=>l.agent_id===a.id)]));table('evidenceRows',['Task','Verifier','Result','Currency'],s.evidence.map(e=>[e.task_id,e.kind,e.result,e.stale?'STALE':'CURRENT']));table('decisionRows',['Subject','State','Details'],[...s.decisions.map(d=>[d.name??d.task_id??d.claim_id,d.lifecycle??d.state,d]),...s.claims.filter(c=>c.disposition==='CONFLICTING').map(c=>[c.subject,c.disposition,c])]);table('requirementRows',['Requirement','Authority','Detail'],s.requirements.map(r=>[r.name,r.authority,r]));table('evolutionRows',['Entity','Lifecycle','Detail'],s.evolution.map(r=>[r.name,r.lifecycle,r]));table('coverageRows',['Area','Inspected / total','State'],Object.entries(s.project.coverage).map(([k,v])=>[k,`${v.inspected} / ${v.total??'unknown'}`,v.status]));const g=await fetch('/api/assurance');if(g.ok){const v=(await g.json()).data;[['Required obligations',v.totals.required],['Proof debt',v.totals.proof_debt]].forEach(([label,n])=>{const d=document.createElement('div'),x=document.createElement('strong');d.className='metric';d.textContent=label;x.textContent=n;d.append(x);el('metrics').append(d)});table('assuranceRows',['Task','Objective','Required','Proof debt','Decision'],v.tasks.map(r=>[r.task_id,r.objective,r.required,r.proof_debt,r.decision.decision]));table('obligationRows',['Obligation','Claim','Criticality','Origin','State'],v.tasks.flatMap(r=>r.obligations.map(o=>[o.id,o.claim,o.criticality+(o.mandatory?'':' (optional)'),o.derivation,o.status])));}else{table('assuranceRows',['Assurance'],[]);table('obligationRows',['Assurance'],[])}const a=await fetch('/api/timeline');table('activityRows',['Sequence','Action','Actor','Detail'],(await a.json()).data.map(x=>[x.seq,x.action,x.actor,x.payload]));}catch(e){el('error').textContent=e.message}}el('refresh').addEventListener('click',refresh);refresh();"""


def handler(root: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            port = cast(HTTPServer, self.server).server_port
            if self.headers.get("Host") not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
                self.send_error(403)
                return
            route = self.path.partition("?")[0]
            content: Any
            if route in {"/", "/app.css", "/app.js"}:
                content, mime = {
                    "/": (HTML, "text/html"),
                    "/app.css": (CSS, "text/css"),
                    "/app.js": (JS, "text/javascript"),
                }[route]
            elif route in {"/api/status", "/api/timeline", "/api/assurance"}:
                operation = {
                    "/api/status": "status",
                    "/api/timeline": "timeline",
                    "/api/assurance": "assurance_status",
                }[route]
                try:
                    with Plane(root) as plane:
                        content = encode(call(plane, operation, {}))
                except (RuntimeError, OSError, ValueError, sqlite3.Error):
                    self.send_error(503, "Project state unavailable")
                    return
                mime = "application/json"
            else:
                self.send_error(404)
                return
            data = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; frame-ancestors 'none'; base-uri 'none'",
            )
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:
            # Status data and request URLs never become logs containing project secrets.
            return

    return Handler


def server(root: Path, port: int) -> HTTPServer:
    return HTTPServer(("127.0.0.1", port), handler(root))
