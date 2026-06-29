import json
import os
import time
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from copilot.auth import SESSION_DIR
from copilot.batch_login import build_oauth_url, extract_token_from_url, _capture_cookies

admin_router = APIRouter()

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
        .btn-success { background: #107c10; color: white; }
        .btn-success:hover { background: #0b5a0b; }
        .action-area { display: flex; gap: 10px; align-items: center; }
        .input-url { padding: 8px; width: 250px; border: 1px solid #ccc; border-radius: 4px; }
        .guide { background: #fff4ce; border-left: 4px solid #d83b01; padding: 15px; margin-bottom: 20px; font-size: 0.95em; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Windows Copilot API - 多账号管理面板</h1>
        <div class="guide">
            <strong>使用说明：</strong><br>
            1. 点击【弹出登录窗口】，在弹出的新标签页中正常登录微软账号。<br>
            2. 登录完成后，页面会跳转到一个白板安全警告页，请<b>复制此时地址栏里完整的长链接</b>。<br>
            3. 将链接粘贴到对应账号的输入框内，点击【提交并保存】。<br>
            <i>保存成功后，系统会自动热加载该账号，无需重启服务！</i>
        </div>
        
        <div id="account-list">加载中...</div>
    </div>

    <script>
        async function loadAccounts() {
            const res = await fetch('/api/admin/accounts');
            const data = await res.json();
            const container = document.getElementById('account-list');
            container.innerHTML = '';
            
            data.accounts.forEach(acc => {
                const card = document.createElement('div');
                card.className = 'account-card';
                
                const statusHtml = acc.is_logged_in 
                    ? '<span class="status-badge status-ok">已登录 (就绪)</span>' 
                    : '<span class="status-badge status-fail">未登录 (或已过期)</span>';
                    
                const oauthUrl = `/api/admin/oauth_url?email=${encodeURIComponent(acc.email)}`;
                
                let actionHtml = `
                    <div class="action-area">
                        <button class="btn btn-primary" onclick="window.open('${oauthUrl}', '_blank', 'width=600,height=700')">1. 弹出登录窗口</button>
                        <input type="text" id="url_${acc.index}" class="input-url" placeholder="2. 在此粘贴登录后的地址栏URL...">
                        <button class="btn btn-success" onclick="submitUrl(${acc.index}, '${acc.email}')">3. 提交并保存</button>
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

        async function submitUrl(index, email) {
            const urlInput = document.getElementById(`url_${index}`).value;
            if (!urlInput) {
                alert("请先粘贴跳转后的地址栏 URL！");
                return;
            }
            
            const btn = event.target;
            btn.innerText = "处理中 (需几秒抓取Cookie)...";
            btn.disabled = true;
            
            try {
                const res = await fetch('/api/admin/submit_token', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ index: index, email: email, redirect_url: urlInput })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    alert('账号 ' + email + ' 登录并保存成功！已自动热加载。');
                    loadAccounts();
                } else {
                    alert('失败: ' + data.message);
                }
            } catch (e) {
                alert('请求异常: ' + e);
            } finally {
                btn.innerText = "3. 提交并保存";
                btn.disabled = false;
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
            
            # Check login status
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

@admin_router.get("/api/admin/oauth_url")
def get_oauth_url(email: str):
    # Redirect directly to the OAuth URL
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=build_oauth_url())

class SubmitTokenReq(BaseModel):
    index: int
    email: str
    redirect_url: str

@admin_router.post("/api/admin/submit_token")
def submit_token(req: SubmitTokenReq):
    try:
        access_token = extract_token_from_url(req.redirect_url)
        if not access_token:
            return JSONResponse(status_code=400, content={"status": "error", "message": "无法从提供的 URL 中提取 access_token，请确保复制了完整的地址栏链接。"})
        
        # Capture cookies headlessly
        cookies = _capture_cookies()
        
        session_dir = f"{SESSION_DIR}/account_{req.index}"
        os.makedirs(session_dir, exist_ok=True)
        token_path = f"{session_dir}/token.json"
        
        auth = {
            "cookies": cookies,
            "access_token": access_token,
            "identity_type": "microsoft",
            "saved_at": time.time(),
        }
        Path(token_path).write_text(json.dumps(auth, indent=2), encoding="utf-8")
        
        # Trigger hot-reload in api.py
        from server.api import hot_reload_pool
        hot_reload_pool()
        
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
