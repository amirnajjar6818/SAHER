import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./workflow.css";

type RecordItem = {
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
  evidence: string;
  unknowns: string;
  privacy_note: string;
  reviewer: string;
  decision: string;
  template: string;
  history: { at: string; action: string }[];
};
const stages = ["ورودی‌ها", "آماده‌سازی", "بررسی محتوا", "خروجی و بازبینی"];
const categories = [
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
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "اطلاعات واردشده را بررسی کنید",
    );
  }
  return response.json();
}
function App() {
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [stage, setStage] = useState(0);
  const [selected, setSelected] = useState<RecordItem | null>(null);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  async function load() {
    try {
      setRecords(await request(""));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    load();
  }, []);
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
      setNotice("تغییرات ثبت شد.");
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
          value={String(selected?.[key] ?? "")}
          onChange={(e) => field(key, e.target.value)}
        />
      ) : (
        <input
          value={String(selected?.[key] ?? "")}
          onChange={(e) => field(key, e.target.value)}
        />
      )}
    </label>
  );
  return (
    <div className="workflow" dir="rtl">
      <header>
        <strong>ساهر</strong>
        <span>گردش کار محتوا</span>
        <button
          onClick={() => {
            setAdding(true);
            setSelected(null);
            setError("");
            setNotice("");
          }}
        >
          ورود محتوای جدید
        </button>
      </header>
      <main>
        <nav aria-label="مراحل بررسی">
          {stages.map((name, index) => (
            <button
              className={stage === index ? "active" : ""}
              key={name}
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
        </nav>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {notice && <p role="status">{notice}</p>}
        {adding ? (
          <section>
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
                />
              </label>
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
            </form>
          </section>
        ) : selected ? (
          <section>
            <button
              className="back"
              onClick={() => {
                setSelected(null);
                setNotice("");
              }}
            >
              بازگشت به فهرست
            </button>
            <h1>{selected.title}</h1>
            <p>منبع · {selected.source}</p>
            {selected.stage === 0 && (
              <>
                <h2>ثبت اولیه</h2>
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
                {input(
                  "privacy_note",
                  "نتیجهٔ بررسی سلامت و اقدامات حریم خصوصی",
                  true,
                )}
                <p>
                  پوشاندن چهره، پلاک و شناسه‌ها در این نسخه به بررسی و
                  آماده‌سازی دستی فایل نیاز دارد.
                </p>
                <button disabled={busy} onClick={extract}>
                  استخراج متن از فایل
                </button>
                {input("text", "متن استخراج‌شده یا متن‌خوانی دستی", true)}
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
                    {categories.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
                {input("case_name", "نام پرونده یا رویداد مرتبط")}
                {input("evidence", "شواهد، منبع تکمیلی و دلیل ارتباط", true)}
                {input("unknowns", "موارد نامشخص و نیازمند بررسی", true)}
                {input("text", "متن محتوا", true)}
                <p>
                  اطلاعات تکمیلی را با نشانی منبع و زمان بررسی در بخش شواهد ثبت
                  کنید.
                </p>
              </>
            )}
            {selected.stage === 3 && (
              <>
                <h2>بازبینی و خروجی</h2>
                <label>
                  قالب خروجی
                  <select
                    value={selected.template}
                    onChange={(e) => field("template", e.target.value)}
                  >
                    <option value="">انتخاب قالب</option>
                    {[
                      "گردش کار سازمانی",
                      "بازبینی سیاست امنیتی",
                      "بازبینی سیاست فرهنگی و اجتماعی",
                    ].map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </label>
                {input("reviewer", "نام مسئول بازبینی")}
                {input("decision", "تصمیم و دلیل بازبین", true)}
                {input("unknowns", "موارد باز و محدودیت‌های گزارش", true)}
                <p>
                  خروجی این نسخه، پروندهٔ ساختاریافته همراه متن، شواهد و سابقهٔ
                  تغییرات است.
                </p>
                {selected.decision && (
                  <a href={"/api/v1/workflow/" + selected.id + "/export"}>
                    دریافت آخرین گزارش ثبت‌شده
                  </a>
                )}
              </>
            )}
            <div className="actions">
              <button
                className="primary"
                disabled={busy}
                onClick={() => save()}
              >
                ثبت تغییرات
              </button>
              {selected.stage < 3 && (
                <button
                  disabled={busy}
                  onClick={() => save(selected.stage + 1)}
                >
                  ثبت و رفتن به مرحلهٔ بعد
                </button>
              )}
              {selected.stage > 0 && (
                <button
                  disabled={busy}
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
                </p>
              ))}
            </details>
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
