#!/usr/bin/env python3
"""
صفحة رفع ملفات محلية من الهاتف إلى الحاسوب — بدون أي خدمات خارجية.
- افتح http://<LAN-IP>:8766/ من هاتفك على نفس شبكة Wi-Fi.
- الملفات تُحفظ في ~/Downloads/incoming/ بأسماء فريدة (بريفة زمنية).
- خيارات: --stop (إيقاف الخادم)، --port N (منفذ بديل).
"""
from __future__ import annotations

import argparse
import email
import json
import os
import re
import socket
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path.home()
INCOMING = HOME / "Downloads" / "incoming"
PID_FILE = HOME / ".cache" / "phone-upload.pid"
MAX_BYTES = 200 * 1024 * 1024  # 200MB

PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>رفع ملف إلى الحاسوب</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: "Segoe UI", Tahoma, Arial, sans-serif; background: #f5f7fa; color: #1a2333; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 16px; }
  .box { background: #fff; border: 1px solid #e3e8ef; border-radius: 16px; box-shadow: 0 4px 16px rgba(16,42,67,.08); padding: 24px; width: 100%; max-width: 460px; text-align: center; }
  h1 { font-size: 1.2rem; margin-bottom: 6px; color: #0d2b4e; }
  p.sub { color: #5b6b7f; font-size: .85rem; margin-bottom: 18px; }
  #drop { border: 2px dashed #9fb3c8; border-radius: 12px; padding: 26px 12px; color: #5b6b7f; font-size: .9rem; margin-bottom: 14px; transition: .2s; }
  #drop.on { border-color: #1565c0; background: #e8f1fc; color: #1565c0; }
  input[type=file] { display: none; }
  button { width: 100%; background: #0d2b4e; color: #fff; border: 0; border-radius: 10px; padding: 13px; font-size: 1rem; cursor: pointer; }
  button:disabled { opacity: .5; }
  #bar { height: 8px; background: #e3e8ef; border-radius: 6px; margin-top: 14px; overflow: hidden; display: none; }
  #bar i { display: block; height: 100%; width: 0; background: #1565c0; transition: width .3s; }
  #res { margin-top: 12px; font-size: .85rem; color: #0a7d33; white-space: pre-wrap; text-align: right; }
  #res.err { color: #c62828; }
</style>
</head>
<body>
<div class="box">
  <h1>رفع ملف إلى الحاسوب</h1>
  <p class="sub">الملفات تُحفظ في مجلد <b>~/Downloads/incoming</b> على الحاسوب</p>
  <div id="drop">اضغط لاختيار ملف أو أسقطه هنا<br>(يدعم ملفات متعددة)</div>
  <input type="file" id="file" multiple>
  <button id="btn">رفع</button>
  <div id="bar"><i></i></div>
  <div id="res"></div>
</div>
<script>
const drop = document.getElementById('drop'), inp = document.getElementById('file'),
      btn = document.getElementById('btn'), bar = document.getElementById('bar'),
      res = document.getElementById('res');
drop.onclick = () => inp.click();
drop.ondragover = e => { e.preventDefault(); drop.classList.add('on'); };
drop.ondragleave = () => drop.classList.remove('on');
drop.ondrop = e => { e.preventDefault(); drop.classList.remove('on'); inp.files = e.dataTransfer.files; };
btn.onclick = async () => {
  if (!inp.files.length) { res.className='err'; res.textContent = 'اختر ملفا أولا'; return; }
  const fd = new FormData();
  for (const f of inp.files) fd.append('files', f);
  res.textContent = ''; bar.style.display = 'block'; btn.disabled = true;
  try {
    const r = await fetch('/upload', { method: 'POST', body: fd });
    const txt = await r.text();
    bar.style.display = 'none';
    res.className = r.ok ? '' : 'err';
    res.textContent = txt;
  } catch (e) {
    bar.style.display = 'none'; res.className = 'err'; res.textContent = 'فشل الاتصال بالحاسوب';
  }
  btn.disabled = false;
};
</script>
</body>
</html>"""


def sanitize(name: str) -> str:
    name = os.path.basename(name or "file")
    name = re.sub(r"[^\w.\- ]+", "_", name)
    return name[:120] or "file"


def detect_lan_ip() -> str:
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show", "scope", "global"],
                             capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "inet" and i + 1 < len(parts):
                    return parts[i + 1].split("/")[0]
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class Handler(BaseHTTPRequestHandler):
    server_version = "PhoneUpload/1.0"

    def log_message(self, fmt, *args):  # تقليل الضجيج
        sys.stderr.write(f"[upload] {time.strftime('%H:%M:%S')} {fmt % args}\n")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] == "/":
            return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        return self._send(404, b"Not found", "text/plain")

    def do_POST(self):
        if self.path.split("?")[0] != "/upload":
            return self._send(404, b"Not found", "text/plain")
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BYTES:
            return self._send(413, "الملف أكبر من الحد المسموح (200MB)".encode("utf-8"),
                              "text/plain; charset=utf-8")
        body = self.rfile.read(length) if length else b""
        INCOMING.mkdir(parents=True, exist_ok=True)
        saved = []
        try:
            raw = (("Content-Type: " + (self.headers.get("Content-Type") or ""))
                   .encode("utf-8") + b"\r\n\r\n" + body)
            msg = email.message_from_bytes(raw)
            parts = msg.get_payload() if msg.is_multipart() else [msg]
            for part in parts:
                disp = part.get("Content-Disposition", "")
                m = re.search(r'filename="([^"]*)"', disp) or re.search(r"filename=([^;]+)", disp)
                if not m:
                    continue
                fname = sanitize(m.group(1).strip().strip('"'))
                data = part.get_payload(decode=True) or b""
                if not data:
                    continue
                ts = time.strftime("%Y%m%d_%H%M%S")
                target = INCOMING / f"{ts}_{fname}"
                n = 1
                while target.exists():
                    target = INCOMING / f"{ts}_{n}_{fname}"
                    n += 1
                target.write_bytes(data)
                saved.append(f"{fname} ← {target}")
        except Exception as exc:
            return self._send(500, f"خطأ في المعالجة: {exc}".encode("utf-8"),
                              "text/plain; charset=utf-8")
        if not saved:
            return self._send(400, "لم يُستلم أي ملف (تحقق من النموذج)".encode("utf-8"),
                              "text/plain; charset=utf-8")
        size = sum(p.stat().st_size for p in map(Path, [s.split(" ← ")[1] for s in saved]))
        ok = "تم الرفع بنجاح\n" + "\n".join(s for s in saved) + f"\nالحجم: {size:,} بايت"
        self._send(200, ok.encode("utf-8"), "text/plain; charset=utf-8")


def running_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip().split()[0])
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        return None


def main() -> int:
    p = argparse.ArgumentParser(description="صفحة رفع ملفات محلية من الهاتف")
    p.add_argument("--stop", action="store_true", help="إيقاف الخادم")
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()

    if args.stop:
        pid = running_pid()
        if pid:
            os.kill(pid, 15)
            try:
                PID_FILE.unlink()
            except OSError:
                pass
            print(f"تم إيقاف خادم الرفع (PID {pid}).")
        else:
            print("لا يوجد خادم رفع قيد التشغيل.")
        return 0

    if args.child:
        INCOMING.mkdir(parents=True, exist_ok=True)
        server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
        server.serve_forever()
        return 0

    if running_pid():
        print("خادم الرفع يعمل بالفعل.")
        return 0

    INCOMING.mkdir(parents=True, exist_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", args.port))
        except OSError:
            print(f"المنفذ {args.port} مشغول — استخدم --port آخر.")
            return 1
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()),
         "--port", str(args.port), "--child"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)
    PID_FILE.write_text(f"{proc.pid} {args.port}", encoding="utf-8")
    ip = detect_lan_ip()
    url = f"http://{ip}:{args.port}/"
    print(f"خادم الرفع يعمل: {url}")
    print(f"الملفات تُحفظ في: {INCOMING}")
    try:
        qr = subprocess.run(["qrencode", "-t", "ANSIUTF8", url],
                            capture_output=True, text=True, timeout=10)
        if qr.returncode == 0 and qr.stdout:
            print(qr.stdout)
    except Exception:
        pass
    print("امسح الرمز من هاتفك (نفس شبكة Wi-Fi) — الإيقاف: --stop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
