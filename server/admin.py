import json
import os
import time
import threading
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from copilot.auth import SESSION_DIR

admin_router = APIRouter()

# Global state for login tasks
_login_tasks = {}

def playwright_login_task(index: int, email: str):
    """Run BrowserCopilot.login() to let the user sign in on copilot.microsoft.com.
    It automatically captures the ChatAI.ReadWrite token and cookies once the user signs in.
    """
    _login_tasks[index] = {"status": "running", "message": "浏览器已弹出，请手动点击【Sign in/登录】并完成验证..."}
    try:
        from copilot.browser import BrowserCopilot
        
        session_dir = f"{SESSION_DIR}/account_{index}"
        profile_dir = f"{session_dir}/profile"
        token_path = f"{session_dir}/token.json"
        os.makedirs(session_dir, exist_ok=True)
        
        # Initialize BrowserCopilot (headless=False so user can see and solve CAPTCHAs)
        bot = BrowserCopilot(profile_dir=profile_dir, headless=False)
        
        # bot.login() will navigate to copilot.microsoft.com and wait for sign-in detection
        auth = bot.login(path=token_path, timeout=300)
        
        if auth and auth.get("access_token"):
            from server.api import hot_reload_pool
            hot_reload_pool()
            _login_tasks[index] = {"status": "success", "message": "登录完成并已自动热加载！"}
        else:
            _login_tasks[index] = {"status": "error", "message": "未能在规定时间内捕获到凭证（可能您未完成登录或手动关闭了窗口）。"}
            
    except Exception as e:
        _login_tasks[index] = {"status": "error", "message": f"出现异常: {str(e)}"}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Windows Copilot API - 多账号管理面板</title>
    <meta charset="utf-8">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #f5f7f9; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 900px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        h1 { color: #0078d4; border-bottom: 2px solid #0078d4; padding-bottom: 10px; }
        .account-card { border: 1px solid #e1dfdd; border-radius: 6px; padding: 15px; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center; background: #faf9f8; }
        .account-info { flex: 1; }
        .account-email { font-size: 1.1em; font-weight: bold; margin-bottom: 5px; }
        .status-badge { display: inline-block; padding: 4px 8px; border-radius: 12px; font-size: 0.85em; font-weight: 600; }
        .status-ok { background: #dff6dd; color: #107c10; }
        .status-fail { background: #fde7e9; color: #a4262c; }
        .btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 14px; transition: background 0.2s; }
        .btn-primary { background: #0078d4; color: white; }
        .btn-primary:hover { background: #106ebe; }
        .guide { background: #fff4ce; border-left: 4px solid #d83b01; padding: 15px; margin-bottom: 20px; font-size: 0.95em; }
        .task-msg { margin-top: 8px; font-size: 0.9em; color: #d83b01; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Windows Copilot API - 多账号管理面板</h1>
        <div class="guide">
            <strong>最佳实践登录流程：</strong><br>
            1. 点击【一键唤起登录】，系统会为您弹出微软 Copilot 官网窗口。<br>
            2. 请在弹出的页面右上角手动点击 <b>Sign In (登录)</b>。<br>
            3. 输入您的微软账号和密码，完成所有人机验证和双重验证。<br>
            4. 登录完成后，您<b>什么都不用做</b>，后台监听器会自动截获带有 ChatAI.ReadWrite 权限的专属 Token 和全套 Cookie。<br>
            <i>截获成功后浏览器会瞬间自毁关闭，同时服务自动热加载该账号！</i>
        </div>
        
        <div id="account-list">加载中...</div>
    </div>

    <script>
        let pollingIntervals = {};

        async function loadAccounts() {
            const res = await fetch('/api/admin/accounts');
            const data = await res.json();
            const container = document.getElementById('account-list');
            container.innerHTML = '';
            
            data.accounts.forEach(acc => {
                const card = document.createElement('div');
                card.className = 'account-card';
                card.id = `card_${acc.index}`;
                
                const statusHtml = acc.is_logged_in 
                    ? '<span class="status-badge status-ok">已登录 (就绪)</span>' 
                    : '<span class="status-badge status-fail">未登录 (或已过期)</span>';
                    
                let actionHtml = `
                    <div>
                        <button class="btn btn-primary" id="btn_${acc.index}" onclick="startAutoLogin(${acc.index}, '${acc.email}')">🚀 一键唤起登录</button>
                        <div id="msg_${acc.index}" class="task-msg"></div>
                    </div>
                `;
                
                card.innerHTML = `
                    <div class="account-info">
                        <div class="account-email">${acc.email}</div>
                        <div>${statusHtml}</div>
                    </div>
                    ${actionHtml}
                `;
                container.appendChild(card);
            });
        }

        async function startAutoLogin(index, email) {
            const btn = document.getElementById(`btn_${index}`);
            const msg = document.getElementById(`msg_${index}`);
            btn.disabled = true;
            btn.innerText = "处理中...";
            
            await fetch('/api/admin/start_login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ index: index, email: email })
            });
            
            pollingIntervals[index] = setInterval(() => checkStatus(index), 1000);
        }

        async function checkStatus(index) {
            const res = await fetch(`/api/admin/task_status?index=${index}`);
            const data = await res.json();
            const msg = document.getElementById(`msg_${index}`);
            const btn = document.getElementById(`btn_${index}`);
            
            if (data.status) {
                msg.innerText = data.message;
                if (data.status === 'success' || data.status === 'error') {
                    clearInterval(pollingIntervals[index]);
                    btn.disabled = false;
                    btn.innerText = "🚀 重新一键唤起";
                    if (data.status === 'success') {
                        setTimeout(loadAccounts, 1500);
                    }
                }
            }
        }

        window.onload = loadAccounts;
    </script>
</body>
</html>
"""

@admin_router.get("/admin", response_class=HTMLResponse)
def admin_page():
    return HTML_TEMPLATE

@admin_router.get("/api/admin/accounts")
def get_accounts():
    accounts = []
    if os.path.exists("accounts.txt"):
        with open("accounts.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line or "----" not in line:
                continue
            email = line.split("----")[0].strip()
            
            is_logged_in = False
            token_path = Path(f"{SESSION_DIR}/account_{i}/token.json")
            if token_path.exists():
                try:
                    data = json.loads(token_path.read_text(encoding="utf-8"))
                    if data.get("access_token") and data.get("cookies"):
                        is_logged_in = True
                except:
                    pass
            
            accounts.append({
                "index": i,
                "email": email,
                "is_logged_in": is_logged_in
            })
    return {"accounts": accounts}

class StartLoginReq(BaseModel):
    index: int
    email: str

@admin_router.post("/api/admin/start_login")
def start_login(req: StartLoginReq):
    threading.Thread(target=playwright_login_task, args=(req.index, req.email), daemon=True).start()
    return {"status": "started"}

@admin_router.get("/api/admin/task_status")
def task_status(index: int):
    task = _login_tasks.get(index, {})
    return JSONResponse(content=task)
