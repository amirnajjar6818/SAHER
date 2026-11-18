import React, { useState } from "react";

export function CaseAccess({ cases, request }: { cases: {id:string;name:string}[]; request: (path:string, options?:RequestInit)=>Promise<any> }) {
  const [caseId, setCase] = useState("");
  const [members, setMembers] = useState<{username:string;permission:string}[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function load(id:string) { setMembers(await request(`/cases/${id}/members`)); }
  return <details><summary>دسترسی پرونده‌ها و رویدادها</summary>
    <p>محتوای بدون پرونده خصوصی است. اعضای مشاهده‌گر فقط می‌خوانند؛ اعضای ویرایشگر تغییرات را ثبت می‌کنند. مدیر به همهٔ پرونده‌ها دسترسی دارد.</p>
    <label>پرونده<select value={caseId} disabled={busy} onChange={async e=>{
      const id=e.target.value; setCase(id); setMembers([]); setMessage("");
      if(id) { setBusy(true); try { await load(id); } catch(e){setMessage((e as Error).message);} finally{setBusy(false);} }
    }}><option value="">انتخاب پرونده</option>{cases.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
    {caseId && <><form onSubmit={async e=>{
      e.preventDefault(); const values=Object.fromEntries(new FormData(e.currentTarget)); setBusy(true); setMessage("");
      try { await request(`/cases/${caseId}/members/${encodeURIComponent(String(values.username))}`, {method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({permission:values.permission})}); await load(caseId); setMessage("دسترسی ثبت شد."); }
      catch(e){setMessage((e as Error).message);} finally{setBusy(false);}
    }}><label>نام کاربری<input name="username" required /></label><label>دسترسی<select name="permission"><option value="viewer">مشاهده</option><option value="editor">ویرایش</option></select></label><button disabled={busy}>ثبت دسترسی</button></form>
    {members.map(m=><p key={m.username}>{m.username} · {m.permission==="editor"?"ویرایش":"مشاهده"} <button disabled={busy} onClick={async()=>{
      setBusy(true); try{await request(`/cases/${caseId}/members/${encodeURIComponent(m.username)}`,{method:"DELETE"});await load(caseId);setMessage("دسترسی لغو شد.");}catch(e){setMessage((e as Error).message);}finally{setBusy(false);}
    }}>لغو دسترسی</button></p>)}</>}
    {message && <p role="status">{message}</p>}
  </details>;
}
