# 🚀 Windows Copilot API (Custom Optimization Edition)

<p align="center">
  <a href="https://github.com/liwei9745/windows-copilot-api-custom/stargazers"><img src="https://img.shields.io/github/stars/liwei9745/windows-copilot-api-custom?style=flat-square&color=ffd700" alt="GitHub stars"></a>
  <a href="https://github.com/liwei9745/windows-copilot-api-custom/network/members"><img src="https://img.shields.io/github/forks/liwei9745/windows-copilot-api-custom?style=flat-square&color=00ff00" alt="GitHub forks"></a>
  <a href="https://github.com/liwei9745/windows-copilot-api-custom/blob/master/LICENSE"><img src="https://img.shields.io/github/license/liwei9745/windows-copilot-api-custom?style=flat-square" alt="GitHub license"></a>
</p>

🇨🇳 **[中文文档 | Chinese Documentation](README.md)**

> 💡 **Credits & Notice**:
> This project is a customized secondary creation based on the excellent original work [Windows-Copilot-API](https://github.com/vladkens/windows-copilot-api) by **vladkens**. 
> Huge thanks to the original author for their outstanding contribution and selfless open-sourcing!

---

## 🎯 Project Goals & Features

### 📌 Goals
Convert your standard **Microsoft Copilot Personal Account** into a high-availability, zero-cost, and zero-threshold **OpenAI-compatible API (Chat Completions API)**. No API key or paid subscriptions are required. You can call Copilot's underlying model and trigger image generation directly in any third-party client (e.g., NextChat, LobeChat, One-API, etc.).

### ✨ Features
* **【Non-standard Port】**: Default port has been optimized and changed to `18521` (from `8000`), reducing conflict with standard ports and improving deploy privacy.
* **【Model Name Spoofing / Rewrite】**: FastAPI routing layer automatically intercepts and rewrites models implicitly. No matter what model name is passed by the client (such as `gpt-4o`, `codex`, `any-model`), the backend will safely rewrite it to `"copilot"`.
* **【Anti-Deadlock Logic】**: Optimized authorization check loop. If credentials are missing or expired, the backend fails fast and alerts immediately instead of hanging headless Chromium indefinitely.
* **【Native Image Generation (DALL-E 3) Rendering】**: When drawing requests (e.g. "draw a cat") are sent, the service will extract generated image URLs and append them as standard Markdown format `![description](url)` to the text output, enabling standard GPT clients to render images inside the chat interface natively.
* **【Multi-platform & Stealth Refresh】**: Login once in a browser on any machine with display support, and the generated `session` can be deployed anywhere. The background worker handles CF challenges and updates token silently in headless mode.

---

## 📊 System Architecture

```mermaid
graph TD
    Client[Client NextChat / LobeChat] -->|1. POST completions request| API[FastAPI Server :18521]
    API -->|2. Rewrite model to copilot| API
    API -->|3. Load Session| Auth{Session Valid?}
    Auth -->|Yes| ClientLib[copilot.client driver]
    Auth -->|No| Headless[Playwright Headless CF Challenge]
    Headless -->|Acquire token & cf_clearance| ClientLib
    ClientLib -->|4. curl_cffi via Local Proxy 10808| Copilot[Microsoft Copilot Web API]
    Copilot -->|5. Return Response| ClientLib
    ClientLib -->|6. Extract DALL-E 3 image URLs| API
    API -->|7. Convert to markdown & Return| Client
```

---

## 📢 Collaboration & Community

* **QQ Group**: `1005859624` (Note: I am not the owner of this group). Welcome to join for discussions!
* **Recommendation**:
  Please check out and support **[chatgpt2api](https://github.com/yukkcat/chatgpt2api)**. Give the author a **Star** and **Fork** 🌟!

---

## 🛠️ Deployment Guide

> ⚠️ **Prerequisite**: Domestic users must make sure the local proxy tool is enabled and configure the correct proxy port (e.g. Clash default `http://127.0.0.1:7890` or `http://127.0.0.1:10808`). The steps below assume the proxy port is `10808`.

### Option 1: Windows Local Deployment

1. **Clone the code**:
   ```bash
   git clone https://github.com/liwei9745/windows-copilot-api-custom.git
   cd windows-copilot-api-custom
   ```
2. **Create & activate Python Virtual Environment**:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. **Install Dependencies & Browser**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```
4. **First-time Login (Authorization)**:
   ```bash
   python -m copilot login
   ```
   *A browser window will pop up. Please log into your Microsoft or Google account. The window closes itself automatically once sign-in is complete.*
5. **Set Proxy & Run**:
   Run the following commands in PowerShell to start the service:
   ```powershell
   $env:HTTP_PROXY="http://127.0.0.1:10808"
   $env:HTTPS_PROXY="http://127.0.0.1:10808"
   $env:ALL_PROXY="socks5://127.0.0.1:10808"
   python app.py
   ```

---

### Option 2: Linux Server Deployment

Since Linux servers usually do not have a graphical interface, we use the **Session Sync Mechanism** to deploy:

1. **Generate Session**: Complete step `4` of **Option 1** on a machine with display to generate the `session` folder.
2. **Clone & Install**:
   Run on your Linux server:
   ```bash
   git clone https://github.com/liwei9745/windows-copilot-api-custom.git
   cd windows-copilot-api-custom
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   playwright install chromium
   ```
3. **Sync Session**: Copy the generated `session` folder from your local machine to the project root folder on the Linux server.
4. **Set Proxy & Start**:
   ```bash
   export HTTP_PROXY="http://127.0.0.1:10808"
   export HTTPS_PROXY="http://127.0.0.1:10808"
   export ALL_PROXY="socks5://127.0.0.1:10808"
   python app.py
   ```

---

### Option 3: Docker Deployment

1. **Sync Session**: Create a `session` folder under the project root, making sure it contains the authorization token generated in the login steps.
2. **Set Compose Proxy** (Optional): If Docker needs to share host proxy:
   ```yaml
   environment:
     HTTP_PROXY: "http://host.docker.internal:10808"
     HTTPS_PROXY: "http://host.docker.internal:10808"
   ```
3. **Build & Run**:
   ```bash
   docker-compose up -d --build
   ```

---

## 🔌 Client Configurations

Please use the following configurations in your client (e.g. NextChat, LobeChat, One-API):

| Configuration | Value |
| :--- | :--- |
| **Base URL** | `http://127.0.0.1:18521/v1` |
| **API Key** | Any virtual key (e.g., `sk-virtual-key`) |
| **Model** | Any model (e.g. `gpt-4o` or `codex`. The backend automatically intercepts and rewrites it to `copilot`) |

*Note: When drawing, please do not attach local image files. Simply write descriptions (e.g., "draw a cute cat").*
