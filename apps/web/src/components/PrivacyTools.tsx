import React, { useState } from "react";

export function PrivacyTools({ text, request, onApply }: {
  text: string;
  request: (path: string, options?: RequestInit) => Promise<any>;
  onApply: (text: string) => void;
}) {
  const [preview, setPreview] = useState<{ text: string; count: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  return <details>
    <summary>پوشاندن اطلاعات شخصی متن</summary>
    <p>ایمیل‌ها، شماره‌های همراه و عددهای ده‌رقمی شناسایی می‌شوند. نام‌ها و عبارت‌های دیگر را هرکدام در یک خط وارد کنید. پیش‌نمایش را پیش از اعمال بررسی کنید.</p>
    <form onSubmit={async (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      setBusy(true); setMessage(""); setPreview(null);
      try {
        setPreview(await request("/privacy", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text, terms: String(data.get("terms")).split("\n").map((s) => s.trim()).filter(Boolean),
          }),
        }));
      } catch (e) { setMessage((e as Error).message); }
      finally { setBusy(false); }
    }}>
      <label>نام‌ها و عبارت‌ها<textarea name="terms" /></label>
      <button disabled={busy || !text.trim()}>ساخت پیش‌نمایش پوشاندن متن</button>
    </form>
    {message && <p role="alert">{message}</p>}
    {preview && <>
      <p>{preview.count.toLocaleString("fa-IR")} مورد پوشانده شد.</p>
      <p className="content-text">{preview.text}</p>
      <button disabled={busy} onClick={() => { onApply(preview.text); setPreview(null); }}>
        اعمال متن پوشانده‌شده در فرم
      </button>
    </>}
  </details>;
}
