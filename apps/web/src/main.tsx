import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { WorkflowAdmin } from "./components/WorkflowAdmin";
import { OnlineSettings, OnlineTools } from "./components/OnlineTools";
import { PrivacyTools } from "./components/PrivacyTools";
import "./workflow.css";
import { BulkImages } from "./components/BulkImages";
import { AccountOrganizer, AccountRecord, platformNames } from "./components/AccountOrganizer";
import { CaseAccess } from "./components/CaseAccess";
import { FileSecurity, SecurityRecord } from "./components/FileSecurity";

type RecordItem = SecurityRecord & AccountRecord & {
  id: string;
  title: string;
  source: string;
  permission: string;
  stage: number;
  version: number;
  created: string;
  text: string;
  category: string;
  case_name: string;
  case_id?: string | null;
  evidence: string;
  unknowns: string;
  analysis?: string;
  privacy_note: string;
  reviewer: string;
  decision: string;
  review_verified?: boolean;
  file_check?: { signature_valid: boolean; mime: string; detail: string | null };
  template: string;
  history: { at: string; action: string }[];
};
type CaseItem = { id: string; kind: "case" | "event"; name: string };
const stages = ["ورودی‌ها", "آماده‌سازی", "بررسی محتوا", "خروجی و بازبینی"];
const defaultCategories = [
  "اجتماعی",
  "اقتصادی",
  "امنیتی",
  "جاسوسی",
  "دفاعی",
  "دین و روحانیت",
  "رزمایش",
  "سایبری",
  "سیاسی",
  "علم و فناوری",
  "فرهنگی",
  "هواگرد",
  "سایر",
];
async function request(path: string, options?: RequestInit) {
  const response = await fetch("/api/v1/workflow" + path, options);
  if (!response.ok) {
    const body = await response.json();
    const credentialError = Array.isArray(body.detail) ? body.detail.find((item: {loc?: string[]}) =>
      item.loc?.includes("password") || item.loc?.includes("username")) : null;
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : credentialError?.loc?.includes("password")
          ? "گذرواژه باید بین ۱۲ تا ۲۵۶ نویسه داشته باشد."
          : credentialError?.loc?.includes("username")
            ? "نام کاربری باید حداکثر ۸۰ نویسه و شامل حروف انگلیسی، عدد، نقطه، خط تیره یا زیرخط باشد."
        : "اطلاعات واردشده را بررسی کنید",
    );
  }
  return response.json();
}
function App() {
  const [auth, setAuth] = useState<{ configured: boolean; user: { username: string; role: string } | null } | null>(null);
  const [settings, setSettings] = useState({
    categories: defaultCategories,
    templates: ["گردش کار سازمانی", "بازبینی سیاست امنیتی", "بازبینی سیاست فرهنگی و اجتماعی"],
    sources: [] as string[],
  });
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [stage, setStage] = useState(0);
  const [selected, setSelected] = useState<RecordItem | null>(null);
  const [adding, setAdding] = useState(false);
  const [foldersView, setFoldersView] = useState(true);
  const [folder, setFolder] = useState("");
  const [topic, setTopic] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [cases, setCases] = useState<CaseItem[]>([]);
  async function load() {
    try {
      setRecords(await request(""));
      setCases(await request("/cases"));
      setSettings(await request("/settings"));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    request("/auth/status").then(setAuth).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (auth?.user) load();
  }, [auth?.user?.username]);
  function field(key: keyof RecordItem, value: string) {
    if (selected) setSelected({ ...selected, [key]: value });
  }
  async function save(next = selected?.stage) {
    if (!selected || next === undefined) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const saved = await request("/" + selected.id, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...selected, stage: next }),
      });
      setSelected(saved);
      setStage(saved.stage);
      await load();
      setNotice(
        selected.decision && !saved.decision
          ? "تغییرات ثبت شد. برای دریافت گزارش، تصمیم بازبین را دوباره ثبت کنید."
          : "تغییرات ثبت شد.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function createCase(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = event.currentTarget;
    const values = new FormData(form);
    setBusy(true);
    setError("");
    try {
      const item: CaseItem = await request("/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: values.get("name"), kind: values.get("kind") }),
      });
      setCases((items) => [...items, item]);
      setSelected((record) =>
        record?.id === selected.id ? { ...record, case_id: item.id, case_name: item.name } : record,
      );
      form.reset();
      setNotice("پرونده یا رویداد ایجاد شد. برای ثبت پیوند، تغییرات محتوا را ذخیره کنید.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function extract() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const result = await request("/" + selected.id + "/extract", {
        method: "POST",
      });
      field("text", result.text);
      setNotice("متن استخراج شد. برای نگهداری، ثبت تغییرات را بزنید.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const input = (key: keyof RecordItem, label: string, multiline = false) => (
    <label>
      {label}
      {multiline ? (
        <textarea
          disabled={busy || selected?.can_edit === false}
          value={String(selected?.[key] ?? "")}
          onChange={(e) => field(key, e.target.value)}
        />
      ) : (
        <input
          disabled={busy || selected?.can_edit === false}
          value={String(selected?.[key] ?? "")}
          onChange={(e) => field(key, e.target.value)}
        />
      )}
    </label>
  );
  if (!auth?.user) return (
    <main dir="rtl"><section>
      <h1>{auth?.configured === false ? "راه‌اندازی مدیر ساهر" : "ورود به ساهر"}</h1>
      {error && <p role="alert">{error}</p>}
      {!auth ? <p>در حال دریافت وضعیت ورود</p> : (
        <form onSubmit={async (event) => {
          event.preventDefault();
          const credentials = Object.fromEntries(new FormData(event.currentTarget));
          setBusy(true);
          setError("");
          try {
            const password = String(credentials.password ?? "");
            if (password.length < 12 || password.length > 256) {
              throw new Error(`گذرواژهٔ واردشده ${password.length.toLocaleString("fa-IR")} نویسه دارد؛ باید بین ۱۲ تا ۲۵۶ نویسه باشد.`);
            }
            if (!auth.configured) await request("/auth/setup", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify(credentials),
            });
            const user = await request("/auth/login", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify(credentials),
            });
            setAuth({ configured: true, user });
          } catch (e) {
            setError((e as Error).message);
            const state = await request("/auth/status");
            setAuth(state);
          } finally { setBusy(false); }
        }}>
          <label>نام کاربری<input name="username" required maxLength={80} pattern="[a-zA-Z0-9_.-]+" autoComplete="username" /></label>
          <label>گذرواژه<input name="password" type="password" required minLength={12} maxLength={256} autoComplete={auth.configured ? "current-password" : "new-password"} /></label>
          <p>گذرواژه باید دست‌کم ۱۲ نویسه داشته باشد.</p>
          <button disabled={busy}>{auth.configured ? "ورود" : "ایجاد مدیر و ورود"}</button>
        </form>
      )}
    </section></main>
  );
  return (
    <div className="workflow" dir="rtl">
      <header>
        <strong>ساهر</strong>
        <span>گردش کار محتوا</span>
        <button disabled={busy} onClick={async () => {
          try {
            await request("/auth/logout", { method: "POST" });
            setRecords([]); setCases([]); setSelected(null); setAdding(false);
            setAuth({ configured: true, user: null });
          } catch (e) { setError((e as Error).message); }
        }}>خروج {auth.user.username}</button>
        <button
          disabled={busy}
          onClick={() => {
            setAdding(true);
            setSelected(null);
            setError("");
            setNotice("");
          }}
        >
          ورود گروهی عکس‌ها
        </button>
      </header>
      <main>
        {auth.user.role === "admin" && (
          <>
            <WorkflowAdmin settings={settings} request={request} onSaved={setSettings} />
            <OnlineSettings request={request} />
            <CaseAccess cases={cases} request={request} />
          </>
        )}
        <div className="actions"><button disabled={busy} className={foldersView?"primary":""} onClick={()=>{setFoldersView(true);setSelected(null);setAdding(false);}}>پوشه‌های حساب‌ها</button><button disabled={busy} onClick={()=>{setFoldersView(false);setSelected(null);setAdding(false);}}>گردش بازبینی محتوا</button></div>
        {!foldersView && <nav aria-label="مراحل بررسی">
          {stages.map((name, index) => (
            <button
              className={stage === index ? "active" : ""}
              key={name}
              disabled={busy}
              onClick={() => {
                setStage(index);
                setSelected(null);
                setNotice("");
                setError("");
              }}
            >
              <span>{(index + 1).toLocaleString("fa-IR")}</span>
              {name}
              <small>
                {records
                  .filter((r) => r.stage === index)
                  .length.toLocaleString("fa-IR")}
              </small>
            </button>
          ))}
        </nav>}
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {notice && <p role="status">{notice}</p>}
        {adding ? (
          <><BulkImages request={request} cases={cases} onBusy={setBusy} onDone={load} />
          <section><button disabled={busy} onClick={()=>{setAdding(false);setFoldersView(true);}}>بازگشت به پوشه‌ها</button><details><summary>ثبت تک‌فایل یا قالب‌های دیگر</summary>
            <h1>ورود محتوا</h1>
            <p>فایل، منبع و مجوز پردازش را ثبت کنید.</p>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                const form = new FormData(e.currentTarget);
                setBusy(true);
                setError("");
                try {
                  const item = await request("", {
                    method: "POST",
                    body: form,
                  });
                  setSelected(item);
                  setStage(0);
                  setAdding(false);
                  await load();
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <label>
                فایل
                <input name="file" type="file" required />
              </label>
              <label>
                منبع
                <input
                  name="source"
                  required
                  placeholder="نام منبع یا نشانی آن"
                  list="sources"
                />
                <datalist id="sources">{settings.sources.map((source) => <option key={source} value={source} />)}</datalist>
              </label>
              <label>پرونده یا رویداد<select name="case_id"><option value="">خصوصی؛ بدون پرونده</option>{cases.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
              <label>
                مجوز پردازش
                <textarea
                  name="permission"
                  required
                  placeholder="مبنای مجازبودن پردازش این محتوا"
                />
              </label>
              <div className="actions">
                <button disabled={busy} className="primary">
                  ثبت محتوا
                </button>
                <button type="button" onClick={() => setAdding(false)}>
                  انصراف
                </button>
              </div>
            </form></details>
          </section></>
        ) : selected ? (
          <section>
            <button
              className="back"
              disabled={busy}
              onClick={() => {
                setSelected(null);
                setNotice("");
              }}
            >
              بازگشت به فهرست
            </button>
            <h1>{selected.title}</h1>
            <p>منبع · {selected.source}</p>
            {selected.antivirus?.status === "clean" && <p><a href={"/api/v1/workflow/" + selected.id + "/original"}>دریافت اصل فایل</a></p>}
            <AccountOrganizer key={selected.id+":"+selected.version} record={selected} categories={settings.categories} request={request} onSaved={(item)=>{setSelected(item);setStage(item.stage);load();}} />
            <FileSecurity key={selected.id} record={selected} request={request} onSaved={(item)=>{setSelected(item);setStage(item.stage);load();}} />
            {selected.stage === 0 && (
              <>
                <h2>ثبت اولیه</h2>
                {selected.file_check && <p>
                  {selected.file_check.signature_valid
                    ? "امضای فایل با قالب پشتیبانی‌شده مطابقت دارد."
                    : selected.file_check.detail}
                </p>}
                <dl>
                  <dt>مجوز پردازش</dt>
                  <dd>{selected.permission}</dd>
                  <dt>زمان ورود</dt>
                  <dd>{new Date(selected.created).toLocaleString("fa-IR")}</dd>
                </dl>
                <p>
                  در مرحلهٔ بعد سلامت فایل و وضعیت اطلاعات شخصی را بررسی کنید.
                </p>
              </>
            )}
            {selected.stage === 1 && (
              <>
                <h2>سلامت و حریم خصوصی</h2>
                <button disabled={busy} onClick={async () => {
                  setBusy(true);
                  setError("");
                  try {
                    const result = await request("/" + selected.id + "/inspect", { method: "POST" });
                    const summary = [
                      result.signature_valid ? "ساختار فایل معتبر است" : result.detail,
                      result.integrity === false ? "هش فایل با زمان ثبت تطابق ندارد" : "",
                      result.scope,
                      result.checked_at,
                    ].filter(Boolean).join("\n");
                    field("privacy_note", [selected.privacy_note, summary].filter(Boolean).join("\n"));
                    setNotice("بررسی فایل انجام شد. نتیجه را بازبینی و ذخیره کنید.");
                  } catch (e) { setError((e as Error).message); }
                  finally { setBusy(false); }
                }}>بررسی ساختار و یکپارچگی فایل</button>
                {input(
                  "privacy_note",
                  "نتیجهٔ بررسی سلامت و اقدامات حریم خصوصی",
                  true,
                )}
                <p>
                  پس از پوشاندن خودکار تصویر و شناسه‌های متن، نتیجه را بازبینی کنید.
                </p>
                <button disabled={busy} onClick={extract}>
                  استخراج متن از فایل
                </button>
                {input("text", "متن استخراج‌شده یا متن‌خوانی دستی", true)}
                <PrivacyTools key={selected.id} text={selected.text} request={request}
                  onApply={(text) => {
                    field("text", text);
                    setNotice("متن پوشانده‌شده در فرم قرار گرفت. آن را بررسی و ذخیره کنید.");
                  }} />
              </>
            )}
            {selected.stage === 2 && (
              <>
                <h2>موضوع، شواهد و ارتباط محتوا</h2>
                <label>
                  موضوع
                  <select
                    value={selected.category}
                    onChange={(e) => field("category", e.target.value)}
                  >
                    <option value="">انتخاب موضوع</option>
                    {Array.from(new Set([...settings.categories, selected.category])).filter(Boolean).map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
                <label>
                  پرونده یا رویداد مرتبط
                  <select
                    value={selected.case_id ?? ""}
                    disabled={busy}
                    onChange={(e) => {
                      const item = cases.find((entry) => entry.id === e.target.value);
                      setSelected({ ...selected, case_id: item?.id ?? null, case_name: item?.name ?? "" });
                    }}
                  >
                    <option value="">بدون پیوند</option>
                    {cases.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.kind === "case" ? "پرونده" : "رویداد"} · {item.name}
                      </option>
                    ))}
                  </select>
                </label>
                {!selected.case_id && selected.case_name && (
                  <p>نام ثبت‌شدهٔ قبلی · {selected.case_name}</p>
                )}
                <details>
                  <summary>ایجاد پرونده یا رویداد</summary>
                  <form onSubmit={createCase}>
                    <label>
                      نوع
                      <select name="kind">
                        <option value="case">پرونده</option>
                        <option value="event">رویداد</option>
                      </select>
                    </label>
                    <label>
                      نام
                      <input name="name" required maxLength={200} />
                    </label>
                    <button disabled={busy}>ایجاد و انتخاب</button>
                  </form>
                </details>
                {input("evidence", "شواهد، منبع تکمیلی و دلیل ارتباط", true)}
                {input("unknowns", "موارد نامشخص و نیازمند بررسی", true)}
                {input("text", "متن محتوا", true)}
                {input("analysis", "یادداشت تحلیل بازبینی‌شده", true)}
                <OnlineTools key={selected.id} text={selected.text} request={request}
                  onAnalysis={(value) => {
                    field("analysis", value);
                    setNotice("پیشنهاد به یادداشت تحلیل افزوده شد. آن را بررسی و تغییرات را ذخیره کنید.");
                  }}
                  onEvidence={(value) => {
                    setSelected((record) => record ? {
                      ...record, evidence: [record.evidence, value].filter(Boolean).join("\n\n"),
                    } : record);
                    setNotice("منبع به فرم افزوده شد. ارتباط آن را بررسی کنید و تغییرات را ذخیره کنید.");
                  }}
                />
                <p>
                  اطلاعات تکمیلی را با نشانی منبع و زمان بررسی در بخش شواهد ثبت
                  کنید.
                </p>
              </>
            )}
            {selected.stage === 3 && (
              <>
                <h2>بازبینی و خروجی</h2>
                <dl>
                  <dt>موضوع</dt><dd>{selected.category}</dd>
                  <dt>پرونده یا رویداد</dt><dd>{selected.case_name || "بدون پیوند"}</dd>
                  <dt>شواهد</dt><dd className="content-text">{selected.evidence}</dd>
                  <dt>متن محتوا</dt><dd className="content-text">{selected.text || "متنی ثبت نشده است"}</dd>
                  <dt>یادداشت تحلیل</dt><dd className="content-text">{selected.analysis || "ثبت نشده است"}</dd>
                  <dt>بررسی سلامت و حریم خصوصی</dt><dd className="content-text">{selected.privacy_note}</dd>
                </dl>
                <label>
                  قالب خروجی
                  <select
                    value={selected.template}
                    onChange={(e) => field("template", e.target.value)}
                  >
                    <option value="">انتخاب قالب</option>
                    {Array.from(new Set([...settings.templates, selected.template])).filter(Boolean).map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
                <p>بازبین هنگام ثبت تصمیم با حساب کاربری احراز هویت می‌شود.</p>
                {selected.reviewer && <p>آخرین بازبین · {selected.reviewer}</p>}
                {input("decision", "تصمیم و دلیل بازبین", true)}
                {selected.unknowns && (
                  <dl>
                    <dt>موارد باز و محدودیت‌های گزارش</dt>
                    <dd>{selected.unknowns}</dd>
                  </dl>
                )}
                <p>
                  خروجی این نسخه، پروندهٔ ساختاریافته همراه متن، شواهد و سابقهٔ
                  تغییرات است.
                </p>
                {records.some((item) => item.id === selected.id && item.decision.trim() && item.review_verified) && (
                  <div className="actions">
                    <a href={"/api/v1/workflow/" + selected.id + "/export"}>دریافت گزارش ساختاریافته</a>
                    <a href={"/api/v1/workflow/" + selected.id + "/export?format=docx"}>دریافت گزارش Word</a>
                  </div>
                )}
              </>
            )}
            <div className="actions">
              <button
                className="primary"
                disabled={busy || selected.can_edit === false}
                onClick={() => save()}
              >
                ثبت تغییرات
              </button>
              {selected.stage < 3 && (
                <button
                  disabled={busy || selected.can_edit === false}
                  onClick={() => save(selected.stage + 1)}
                >
                  ثبت و رفتن به مرحلهٔ بعد
                </button>
              )}
              {selected.stage > 0 && (
                <button
                  disabled={busy || selected.can_edit === false}
                  onClick={() => save(selected.stage - 1)}
                >
                  بازگرداندن برای اصلاح
                </button>
              )}
            </div>
            <details>
              <summary>سابقهٔ تغییرات</summary>
              {selected.history.map((h, i) => (
                <p key={i}>
                  {h.action} · {new Date(h.at).toLocaleString("fa-IR")}
                  {"actor" in h && <span> · {String(h.actor)}</span>}
                </p>
              ))}
            </details>
          </section>
        ) : foldersView ? (
          <section><h1>آرشیو عکس‌ها بر اساس حساب</h1><p>هر پوشه مربوط به آی‌دی تأییدشده در یک شبکه است. دسته‌های داخل پوشه، موضوع عکس‌ها هستند.</p>
            {!folder&&<div className="records account-folders"><button onClick={()=>setFolder("pending")}><strong>در انتظار تأیید حساب</strong><span>{records.filter(r=>!r.account_id&&(r.file_check?.mime.startsWith("image/")||/\.(jpe?g|png|webp|bmp|tiff?)$/i.test(r.title))).length.toLocaleString("fa-IR")} عکس</span></button>{Array.from(new Map(records.filter(r=>r.account_id&&r.account).map(r=>[r.account_id!,r])).values()).map(r=><button key={r.account_id} onClick={()=>{setFolder(r.account_id!);setTopic("");}}><strong>پوشه · <bdi>@{r.account!.handle}</bdi></strong><span>{platformNames[r.account!.platform]} · {r.case_name||"خصوصی"}</span><small>{records.filter(item=>item.account_id===r.account_id).length.toLocaleString("fa-IR")} عکس</small></button>)}</div>}
            <div className="folder-filters"><label>پوشه<select value={folder} onChange={e=>{setFolder(e.target.value);setTopic("");}}><option value="">همهٔ عکس‌ها</option><option value="pending">در انتظار تأیید حساب</option>{Array.from(new Map(records.filter(r=>r.account_id&&r.account).map(r=>[r.account_id!,r])).values()).map(r=><option key={r.account_id} value={r.account_id}>{platformNames[r.account!.platform]} · @{r.account!.handle} {r.case_name?`· ${r.case_name}`:"· خصوصی"}</option>)}</select></label>
            <label>موضوع عکس<select value={topic} onChange={e=>setTopic(e.target.value)}><option value="">همهٔ موضوع‌ها</option><option value="unclassified">بدون موضوع</option>{settings.categories.map(c=><option key={c}>{c}</option>)}</select></label></div>
            <div className="records">{records.filter(r=>r.file_check?.mime.startsWith("image/")||/\.(jpe?g|png|webp|bmp|tiff?)$/i.test(r.title)).filter(r=>!folder||(folder==="pending"?!r.account_id:r.account_id===folder)).filter(r=>!topic||(topic==="unclassified"?!r.category:r.category===topic)).map(r=><button key={r.id} onClick={()=>{setSelected(r);setStage(r.stage);setError("");setNotice("");}}><strong>{r.title}</strong><span>{r.account?<bdi>@{r.account.handle}</bdi>:"منتظر تأیید حساب"}</span><small>{r.category||"بدون موضوع"} · {r.antivirus?.status==="clean"?"اسکن سالم":"قرنطینه"}</small></button>)}</div>
            {!records.length&&<p>با «ورود گروهی عکس‌ها» یک مجموعه عکس اضافه کنید.</p>}
          </section>
        ) : (
          <section>
            <div className="listheading">
              <h1>{stages[stage]}</h1>
              <span>
                {records
                  .filter((r) => r.stage === stage)
                  .length.toLocaleString("fa-IR")}{" "}
                محتوا
              </span>
            </div>
            {records.filter((r) => r.stage === stage).length === 0 ? (
              <div className="empty">
                <h2>محتوایی در این مرحله وجود ندارد</h2>
                <p>با ورود فایل جدید، بررسی را آغاز کنید.</p>
                <button onClick={() => setAdding(true)}>ورود محتوا</button>
              </div>
            ) : (
              <div className="records">
                {records
                  .filter((r) => r.stage === stage)
                  .map((r) => (
                    <button
                      key={r.id}
                      onClick={() => {
                        setSelected(r);
                        setError("");
                        setNotice("");
                      }}
                    >
                      <strong>{r.title}</strong>
                      <span>{r.source}</span>
                      <small>
                        {new Date(r.created).toLocaleDateString("fa-IR")}
                      </small>
                    </button>
                  ))}
              </div>
            )}
          </section>
        )}
        <footer>
          ثبت منبع، بررسی شواهد و تصمیم بازبین در کنار هر محتوا نگهداری می‌شود.
        </footer>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
