import React, { useState } from "react";

export type SecurityRecord = {id:string;version:number;can_edit?:boolean;file_check?:{mime:string};antivirus?:{status:string;engine:string;checked_at:string;signature?:string};redaction?:{confirmed:boolean;width:number;height:number;boxes:any[]}|null};
export function FileSecurity({record,request,onSaved}:{record:SecurityRecord;request:(path:string, options?:RequestInit)=>Promise<any>;onSaved:(record:any)=>void}) {
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [start,setStart]=useState<number[]|null>(null);
  const [box,setBox]=useState<number[]|null>(null);
  async function action(path:string,extra={}) {
    if(record.can_edit===false)return;
    setBusy(true);setError("");
    try{onSaved(await request(`/${record.id}/${path}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({version:record.version,...extra})}));setBox(null);}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  const scan=record.antivirus;
  const labels:Record<string,string>={clean:"سالم",infected:"آلوده و قرنطینه",unavailable:"اسکنر در دسترس نیست؛ قرنطینه",changed:"اصل فایل تغییر کرده است؛ قرنطینه"};
  return <div className="security-tools"><h2>ضدبدافزار و پوشاندن تصویر</h2>
    <p>وضعیت ضدبدافزار: {labels[scan?.status??""]??"اسکن نشده؛ قرنطینه"}</p>
    {scan && <p>{scan.engine} · {new Date(scan.checked_at).toLocaleString("fa-IR")} {scan.signature}</p>}
    <p>{record.can_edit===false?"دسترسی شما به این پرونده فقط مشاهده است.":"پیش از اجرای این عملیات، تغییرات فرم را ثبت کنید."}</p>
    <button disabled={busy||record.can_edit===false} onClick={()=>action("scan")}>{busy?"در حال پردازش…":"اسکن مجدد ضدبدافزار"}</button>
    {scan?.status==="clean" && record.file_check?.mime.startsWith("image/") && <>
      <p>چهره و پلاک در تصاویر ثابت به‌صورت محلی تشخیص داده و با رنگ سیاه پوشانده می‌شوند. تشخیص ممکن است مواردی را جا بیندازد؛ تصویر را بازبینی کنید و نواحی باقی‌مانده را با کشیدن کادر اضافه کنید.</p>
      <button disabled={busy||record.can_edit===false} onClick={()=>action("redact")}>پوشاندن خودکار چهره و پلاک</button>
      {record.redaction && <>
        <p>{record.redaction.boxes.length.toLocaleString("fa-IR")} ناحیه پوشانده شده · {record.redaction.confirmed?"بازبینی تأیید شده":"نیازمند بازبینی"}</p>
        <div className="mask-preview" style={{position:"relative",touchAction:"none",display:"inline-block",maxWidth:"100%"}}>
          <img draggable={false} alt="پیش‌نمایش تصویر پوشانده‌شده؛ برای پوشاندن ناحیهٔ بیشتر کادر بکشید" src={`/api/v1/workflow/${record.id}/redacted?v=${record.version}`} style={{display:"block",maxWidth:"100%",maxHeight:600}} onPointerDown={e=>{
            if(busy||record.can_edit===false)return;const r=e.currentTarget.getBoundingClientRect();const p=[(e.clientX-r.left)/r.width*record.redaction!.width,(e.clientY-r.top)/r.height*record.redaction!.height];setStart(p);setBox(null);e.currentTarget.setPointerCapture(e.pointerId);
          }} onPointerUp={e=>{if(!start)return;const r=e.currentTarget.getBoundingClientRect();const x=Math.max(0,Math.min(record.redaction!.width,(e.clientX-r.left)/r.width*record.redaction!.width));const y=Math.max(0,Math.min(record.redaction!.height,(e.clientY-r.top)/r.height*record.redaction!.height));if(Math.abs(x-start[0])>2&&Math.abs(y-start[1])>2)setBox([Math.min(x,start[0]),Math.min(y,start[1]),Math.max(x,start[0]),Math.max(y,start[1])]);setStart(null);}} />
          {box&&<div style={{position:"absolute",pointerEvents:"none",border:"2px solid #e43",left:`${box[0]/record.redaction.width*100}%`,top:`${box[1]/record.redaction.height*100}%`,width:`${(box[2]-box[0])/record.redaction.width*100}%`,height:`${(box[3]-box[1])/record.redaction.height*100}%`}}/>}
        </div>
        {box&&<button disabled={busy} onClick={()=>action("redact",{boxes:[box]})}>پوشاندن کادر انتخاب‌شده</button>}
        <div className="actions"><button disabled={busy||record.can_edit===false||!!box||record.redaction.confirmed} onClick={()=>action("redact/confirm")}>تصویر را بازبینی کردم؛ تأیید پوشاندن</button><a href={`/api/v1/workflow/${record.id}/redacted`} download="redacted.png">دریافت تصویر پوشانده‌شده</a></div>
      </>}
    </>}
    {error&&<p role="alert">{error}</p>}
  </div>;
}
