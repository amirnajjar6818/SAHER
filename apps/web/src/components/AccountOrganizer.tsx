import React,{useState} from "react";

export type AccountRecord={id:string;version:number;text:string;category:string;can_edit?:boolean;account_id?:string;account?:{platform:string;handle:string};account_candidates?:{platform:string;handle:string;evidence:string}[];file_check?:{mime:string};antivirus?:{status:string}};
export const platformNames:Record<string,string>={instagram:"اینستاگرام",telegram:"تلگرام",x:"ایکس / توییتر",tiktok:"تیک‌تاک",youtube:"یوتیوب",facebook:"فیس‌بوک",unknown:"شبکه نامشخص"};
export function AccountOrganizer({record,categories,request,onSaved}:{record:AccountRecord;categories:string[];request:(path:string,options?:RequestInit)=>Promise<any>;onSaved:(record:any)=>void}){
  const [platform,setPlatform]=useState(record.account?.platform??"");
  const [handle,setHandle]=useState(record.account?.handle??"");
  const [category,setCategory]=useState(record.category);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  async function submit(path:string,values:object){setBusy(true);setError("");try{onSaved(await request(`/${record.id}/${path}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({version:record.version,...values})}));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  if(!record.file_check?.mime.startsWith("image/"))return null;
  return <div className="security-tools"><h2>پوشهٔ حساب و موضوع عکس</h2>
    {record.antivirus?.status==="clean"&&<details><summary>دیدن عکس اصلی برای بررسی آی‌دی</summary><img style={{maxWidth:"100%",maxHeight:600}} loading="lazy" src={`/api/v1/workflow/${record.id}/preview?v=${record.version}`} alt="عکس اصلی برای بازبینی آی‌دی حساب"/></details>}
    <p>پیش از این عملیات، تغییرات فرم را ذخیره کنید.</p>
    <p>آی‌دی داخل عکس ممکن است نام نویسنده، منشن یا حساب بازنشرکننده باشد. ارتباط آن را بررسی کنید؛ این اتصال به معنی شناسایی صاحب چهره یا تأیید هویت واقعی نیست.</p>
    {record.account&&<p>پوشهٔ فعلی: {platformNames[record.account.platform]} · <bdi>@{record.account.handle}</bdi></p>}
    <button disabled={busy||record.can_edit===false||record.antivirus?.status!=="clean"} onClick={()=>submit("analyze-image",{})}>متن‌خوانی و یافتن آی‌دی‌های پیشنهادی</button>
    <fieldset disabled={busy||record.can_edit===false||record.antivirus?.status!=="clean"}>
      {record.account_candidates?.map((candidate,i)=><button type="button" key={i} onClick={()=>{setPlatform(candidate.platform==="unknown"?"":candidate.platform);setHandle(candidate.handle);}}>{platformNames[candidate.platform]} · <bdi>@{candidate.handle}</bdi></button>)}
      <label>شبکهٔ اجتماعی<select value={platform} onChange={e=>setPlatform(e.target.value)}><option value="">انتخاب شبکه</option>{Object.entries(platformNames).filter(([key])=>key!=="unknown").map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></label>
      <label>آی‌دی حساب بدون @<input dir="ltr" value={handle} maxLength={80} onChange={e=>setHandle(e.target.value.replace(/^@/,""))}/></label>
      <label>موضوع خود عکس<select value={category} onChange={e=>setCategory(e.target.value)}><option value="">بدون موضوع؛ نیازمند بررسی</option>{categories.map(c=><option key={c}>{c}</option>)}</select></label>
      <button className="primary" disabled={!platform||!handle} onClick={()=>submit("organize",{platform,handle,category})}>ارتباط را بررسی کردم؛ ثبت در پوشهٔ حساب</button>
    </fieldset>
    {error&&<p role="alert">{error}</p>}
  </div>;
}
