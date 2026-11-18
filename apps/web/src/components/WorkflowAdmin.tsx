import React, { useState } from "react";

type Settings = { categories: string[]; templates: string[]; sources: string[] };
type Props = {
  settings: Settings;
  request: (path: string, options?: RequestInit) => Promise<any>;
  onSaved: (settings: Settings) => void;
};

export function WorkflowAdmin({ settings, request, onSaved }: Props) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <details>
      <summary>تنظیمات و کاربران</summary>
      {message && <p role="status">{message}</p>}
      <form onSubmit={async (event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        setBusy(true);
        try {
          const values = Object.fromEntries(
            ["categories", "templates", "sources"].map((key) => [
              key, String(data.get(key)).split("\n").map((s) => s.trim()).filter(Boolean),
            ]),
          );
          onSaved(await request("/settings", {
            method: "PUT", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(values),
          }));
          setMessage("تنظیمات ذخیره شد.");
        } catch (error) { setMessage((error as Error).message); }
        finally { setBusy(false); }
      }}>
        <h2>گزینه‌ها</h2>
        <p>هر گزینه را در یک خط وارد کنید.</p>
        <label>موضوع‌ها<textarea name="categories" defaultValue={settings.categories.join("\n")} required /></label>
        <label>مسیرهای بازبینی<textarea name="templates" defaultValue={settings.templates.join("\n")} required /></label>
        <label>منابع پیشنهادی<textarea name="sources" defaultValue={settings.sources.join("\n")} /></label>
        <button disabled={busy}>ذخیره تنظیمات</button>
      </form>
      <form onSubmit={async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const data = Object.fromEntries(new FormData(form));
        setBusy(true);
        try {
          await request("/auth/users", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
          });
          form.reset();
          setMessage("کاربر ایجاد شد.");
        } catch (error) { setMessage((error as Error).message); }
        finally { setBusy(false); }
      }}>
        <h2>ایجاد کاربر</h2>
        <label>نام کاربری<input name="username" required pattern="[a-zA-Z0-9_.-]+" autoComplete="off" /></label>
        <label>گذرواژه<input name="password" type="password" required minLength={12} autoComplete="new-password" /></label>
        <label>نقش<select name="role">
          <option value="editor">ثبت و بررسی محتوا</option>
          <option value="reviewer">بازبین</option>
          <option value="admin">مدیر</option>
        </select></label>
        <button disabled={busy}>ایجاد کاربر</button>
      </form>
    </details>
  );
}
