import React, { useRef, useState } from "react";

type Entry = { file: File; state: "waiting"|"working"|"done"|"quarantine"|"error"; message: string; record?: any };
export function BulkImages({request,cases,onBusy,onDone}:{request:(path:string,options?:RequestInit)=>Promise<any>;cases:{id:string;name:string}[];onBusy:(busy:boolean)=>void;onDone:()=>Promise<void>}) {
  const [entries,setEntries]=useState<Entry[]>([]);
  const [running,setRunning]=useState(false);
  const [error,setError]=useState("");
  const stop=useRef(false);
  function update(index:number,change:Partial<Entry>){setEntries(items=>items.map((item,i)=>i===index?{...item,...change}:item));}
  async function run(event:React.FormEvent<HTMLFormElement>){
    event.preventDefault(); if(running)return;
    const values=new FormData(event.currentTarget);
    stop.current=false;setRunning(true);onBusy(true);setError("");
    try{
      for(let i=0;i<entries.length;i++){
        const entry=entries[i];
        if(stop.current)break;
        if(entry.state!=="waiting")continue;
        update(i,{state:"working",message:"ورود و اسکن ضدبدافزار…"});
        let record=entry.record;
        try{
          if(!record){
            const body=new FormData();body.set("file",entry.file);body.set("source",String(values.get("source")));body.set("permission",String(values.get("permission")));
            if(values.get("case_id"))body.set("case_id",String(values.get("case_id")));
            record=await request("",{method:"POST",body});update(i,{record});
          }
          if(record.antivirus?.status!=="clean"){
            update(i,{state:"quarantine",message:"ثبت شد؛ تا اسکن سالم در قرنطینه است",record});continue;
          }
          if(values.get("ocr")){
            update(i,{message:"متن‌خوانی و جست‌وجوی آی‌دی…"});
            record=await request(`/${record.id}/analyze-image`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({version:record.version})});
          }
          update(i,{state:"done",record,message:record.account_candidates?.length?`${record.account_candidates.length.toLocaleString("fa-IR")} آی‌دی پیشنهادی؛ منتظر تأیید اتصال` : "ثبت شد؛ پوشهٔ حساب را انتخاب یا آی‌دی را دستی وارد کنید"});
        }catch(e){update(i,{state:"error",record,message:(record?"عکس ثبت شد؛ متن‌خوانی کامل نشد. ":"")+(e as Error).message});}
      }
    }finally{setRunning(false);onBusy(false);await onDone();}
  }
  const completed=entries.filter(e=>!["waiting","working"].includes(e.state)).length;
  return <section><h1>ورود گروهی عکس‌ها</h1><p>عکس‌ها را با هم انتخاب کنید. هر عکس جداگانه اسکن و متن‌خوانی می‌شود؛ اتصال به پوشهٔ حساب پس از تأیید شما انجام می‌شود.</p>
    <form onSubmit={run}><fieldset disabled={running}>
      <label>انتخاب عکس‌ها<input type="file" multiple accept="image/jpeg,image/png,image/webp,image/bmp,image/tiff,.jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff" onChange={e=>{
        const files=Array.from(e.target.files??[]);setError("");
        if(files.length>1000){setError("در هر نوبت حداکثر ۱۰۰۰ عکس انتخاب کنید.");setEntries([]);return;}
        setEntries(files.map(file=>({file,state:file.size===0||file.size>25*1024*1024?"error":"waiting",message:file.size===0?"فایل خالی است":file.size>25*1024*1024?"بیشتر از ۲۵ مگابایت":"در انتظار"})));
      }}/></label>
      <label>منبع مشترک<input name="source" required placeholder="مثلاً مجموعهٔ اسکرین‌شات‌های ارسالی"/></label>
      <label>مجوز پردازش<textarea name="permission" required/></label>
      <label>پروندهٔ دسترسی<select name="case_id"><option value="">خصوصی؛ فقط خودم و مدیر</option>{cases.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <label><input name="ocr" type="checkbox" defaultChecked/> استخراج متن و پیشنهاد آی‌دی از تصویر</label>
      <button className="primary" disabled={!entries.some(e=>e.state==="waiting")}>شروع / ادامهٔ ورود گروهی</button>
    </fieldset></form>
    {running&&<button onClick={()=>{stop.current=true;}}>توقف پس از پایان عکس جاری</button>}
    {!!entries.length&&<><p role="status">{completed.toLocaleString("fa-IR")} از {entries.length.toLocaleString("fa-IR")} عکس پردازش شده</p><progress value={completed} max={entries.length}/><p>هنگام ورود گروهی، این صفحه را باز نگه دارید. عکس‌های ثبت‌شده با توقف از بین نمی‌روند.</p>
      <div className="batch-results">{entries.map((entry,i)=><p key={i}><strong>{entry.file.name}</strong> · {entry.message}</p>)}</div></>}
    {error&&<p role="alert">{error}</p>}
  </section>;
}
