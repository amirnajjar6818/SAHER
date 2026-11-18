import React, { useEffect, useState } from "react";

type RequestFunction = (path: string, options?: RequestInit) => Promise<any>;
type Config = { provider: string; model: string; configured: boolean; search_configured: boolean };
export function OnlineSettings({ request }: { request: RequestFunction }) {
  const [config, setConfig] = useState<Config | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { request("/online").then(setConfig).catch((e) => setMessage(e.message)); }, []);
  return <details>
    <summary>سرویس‌های آنلاین</summary>
    {message && <p role="status">{message}</p>}
    {config && <form onSubmit={async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const data = new FormData(form);
      setBusy(true);
      try {
        const saved = await request("/online", {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...Object.fromEntries(data),
            clear_api_key: data.has("clear_api_key"), clear_search_key: data.has("clear_search_key") }),
        });
        setConfig(saved);
        for (const input of form.querySelectorAll<HTMLInputElement>("input[type=password]")) {
          input.value = "";
        }
        for (const input of form.querySelectorAll<HTMLInputElement>("input[type=checkbox]")) {
          input.checked = false;
        }
        setMessage("تنظیمات سرویس آنلاین ذخیره شد.");
      } catch (e) { setMessage((e as Error).message); }
      finally { setBusy(false); }
    }}>
      <label>ارائه‌دهنده تحلیل
        <select name="provider" defaultValue={config.provider}>
          <option value="openai">OpenAI</option><option value="openrouter">OpenRouter</option>
        </select>
      </label>
      <label>شناسه مدل<input name="model" defaultValue={config.model} /></label>
      <label>کلید API تحلیل<input name="api_key" type="password" autoComplete="off" /></label>
      <p>{config.configured ? "کلید تحلیل ثبت شده است." : "تحلیل آنلاین تنظیم نشده است."} فیلد خالی کلید فعلی را حفظ می‌کند. تغییر ارائه‌دهنده به ثبت کلید مربوط به آن نیاز دارد.</p>
      <label><span>حذف کلید تحلیل</span><input name="clear_api_key" type="checkbox" /></label>
      <label>کلید Brave Search<input name="search_key" type="password" autoComplete="off" /></label>
      <p>{config.search_configured ? "کلید جست‌وجو ثبت شده است." : "جست‌وجوی آنلاین تنظیم نشده است."}</p>
      <label><span>حذف کلید جست‌وجو</span><input name="clear_search_key" type="checkbox" /></label>
      <p>کلیدها در فضای دادهٔ محلی سرویس ذخیره می‌شوند و در پاسخ API برگردانده نمی‌شوند.</p>
      <button disabled={busy}>ذخیره سرویس‌های آنلاین</button>
    </form>}
  </details>;
}

type Result = { title: string; url: string; description: string };
export function OnlineTools({ text, request, onEvidence, onAnalysis }: {
  text: string; request: RequestFunction; onEvidence: (value: string) => void;
  onAnalysis: (value: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [analysis, setAnalysis] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [at, setAt] = useState("");
  return <details>
    <summary>تحلیل آنلاین و منابع عمومی</summary>
    <p>با تحلیل آنلاین، متن این فرم به ارائه‌دهندهٔ تنظیم‌شده ارسال می‌شود. جست‌وجو عبارت واردشده را به Brave Search ارسال می‌کند.</p>
    {message && <p role="status">{message}</p>}
    <button disabled={busy || !text.trim()} onClick={async () => {
      setBusy(true); setMessage("");
      try {
        const response = await request("/online/analyze", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        setAnalysis(response.text);
        setMessage(response.provider + " · " + response.model);
      } catch (e) { setMessage((e as Error).message); }
      finally { setBusy(false); }
    }}>ارسال متن برای تحلیل آنلاین</button>
    {analysis && <><h2>پیشنهاد تحلیل برای بازبینی</h2><p className="content-text">{analysis}</p>
      <button disabled={busy} onClick={() => onAnalysis(analysis)}>افزودن به یادداشت تحلیل برای بررسی</button></>}
    <form onSubmit={async (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      setBusy(true); setMessage(""); setResults([]);
      try {
        const response = await request("/online/search", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: data.get("query") }),
        });
        setResults(response.results); setAt(response.at);
        if (!response.results.length) setMessage("نتیجه‌ای پیدا نشد.");
      } catch (e) { setMessage((e as Error).message); }
      finally { setBusy(false); }
    }}>
      <label>عبارت جست‌وجو<input name="query" required maxLength={400} /></label>
      <button disabled={busy}>جست‌وجوی منابع عمومی</button>
    </form>
    {results.map((result) => <article key={result.url}>
      <h2><a href={result.url} target="_blank" rel="noreferrer">{result.title}</a></h2>
      <p>{result.description}</p>
      <button disabled={busy} onClick={() => onEvidence(
        [result.title, result.url, result.description, "زمان دریافت " + at].join("\n"),
      )}>افزودن منبع به شواهد برای بررسی</button>
    </article>)}
  </details>;
}
