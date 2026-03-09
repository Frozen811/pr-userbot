from fastapi import FastAPI, Request, Form, Body, Depends, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn
import asyncio
import secrets
from app import database
import os
from collections import deque
from pydantic import BaseModel

app = FastAPI()

# HTTP Basic Auth
security = HTTPBasic()
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    user_ok = secrets.compare_digest(credentials.username.encode(), ADMIN_USER.encode())
    pass_ok = secrets.compare_digest(credentials.password.encode(), ADMIN_PASS.encode())
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Setup templates
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')
os.makedirs(TEMPLATES_DIR, exist_ok=True)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Shared log buffer
log_buffer = deque(maxlen=50)

# Shared bot state (cycle index survives web restarts, resets on process restart)
bot_state = {"cycle_index": 0}

def add_log(message: str):
    log_buffer.append(message)

# Pydantic models for JSON requests
class CustomChatRequest(BaseModel):
    chat_id: int
    min_delay: int
    max_delay: int

class RemoveCustomChatRequest(BaseModel):
    chat_id: int

class ConfigRequest(BaseModel):
    message_template: str = ""
    message_template_2: str = ""
    message_template_3: str = ""
    broadcast_mode: int = 1
    daily_limit: int = 400
    min_delay: int = 30
    max_delay: int = 60
    cycle_delay_seconds: int = 120

@app.get("/", response_class=HTMLResponse, dependencies=[Depends(verify_credentials)])
async def dashboard(request: Request):
    stats = {}
    stats['total_sent'] = await database.get_stat('total_sent')
    stats['daily_sent'] = await database.get_stat('daily_sent')
    stats['start_date'] = await database.get_stat('start_date')

    chats = await database.get_chats()
    active_chats = sum(1 for c in chats if c['status'] == 'active')
    error_chats = sum(1 for c in chats if c['status'] == 'error')
    
    # Filter for custom chats
    custom_chats = [c for c in chats if c.get('is_custom') == 1]

    settings = await database.get_settings()
    global_min = settings.get('min_delay', 30)
    global_max = settings.get('max_delay', 60)
    is_running = bool(settings.get('is_running', 0))

    return templates.TemplateResponse("index.html", {
        "request": request,
        "tab": "dashboard",
        "stats": stats,
        "active_chats_count": active_chats,
        "error_chats_count": error_chats,
        "total_chats_count": len(chats),
        "limit": settings.get('daily_limit', 400),
        "custom_chats": custom_chats,
        "all_chats": chats,
        "global_min": global_min,
        "global_max": global_max,
        "is_running": is_running,
    })

@app.post("/api/bot/toggle", dependencies=[Depends(verify_credentials)])
async def api_bot_toggle():
    settings = await database.get_settings()
    new_state = not bool(settings.get('is_running', 0))
    await database.set_running_status(new_state)
    return {"is_running": new_state}

@app.get("/api/logs", dependencies=[Depends(verify_credentials)])
async def api_get_logs():
    return JSONResponse(content={"logs": list(log_buffer)})

@app.post("/api/settings/custom_chat", dependencies=[Depends(verify_credentials)])
async def api_set_custom_chat(data: CustomChatRequest):
    await database.update_chat_settings(data.chat_id, True, data.min_delay, data.max_delay)
    return {"status": "success"}

@app.post("/api/settings/config", dependencies=[Depends(verify_credentials)])
async def api_save_config(data: ConfigRequest):
    if data.daily_limit < 0 or data.min_delay < 0 or data.max_delay < 0 or data.cycle_delay_seconds < 0:
        raise HTTPException(status_code=400, detail="Values cannot be negative.")
    if data.min_delay > data.max_delay:
        raise HTTPException(status_code=400, detail="min_delay cannot be greater than max_delay.")
    await database.update_settings(
        template=data.message_template,
        template_2=data.message_template_2,
        template_3=data.message_template_3,
        broadcast_mode=max(1, min(3, data.broadcast_mode)),
        limit=data.daily_limit,
        min_delay=data.min_delay,
        max_delay=data.max_delay,
        cycle_delay=data.cycle_delay_seconds
    )
    return {"status": "success"}

@app.post("/api/settings/remove_custom_chat", dependencies=[Depends(verify_credentials)])
async def api_remove_custom_chat(data: RemoveCustomChatRequest):
    await database.update_chat_settings(data.chat_id, False, 0, 0)
    return {"status": "success"}

@app.get("/logs", response_class=HTMLResponse, dependencies=[Depends(verify_credentials)])
async def logs(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "tab": "logs",
        "logs": list(log_buffer)
    })

@app.get("/chats", response_class=HTMLResponse, dependencies=[Depends(verify_credentials)])
async def chats(request: Request):
    chat_list = await database.get_chats()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "tab": "chats",
        "chats": chat_list
    })

@app.post("/chats/delete", dependencies=[Depends(verify_credentials)])
async def delete_chat(chat_id: int = Form(...)):
    await database.remove_chat(chat_id)
    return RedirectResponse(url="/chats", status_code=303)

@app.get("/config", response_class=HTMLResponse, dependencies=[Depends(verify_credentials)])
async def config_page(request: Request):
    conf = await database.get_settings()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "tab": "config",
        "config": conf
    })

@app.post("/config/update", dependencies=[Depends(verify_credentials)])
async def update_config(
    message_template: str = Form(""),
    message_template_2: str = Form(""),
    message_template_3: str = Form(""),
    broadcast_mode: int = Form(1),
    daily_limit: int = Form(400),
    min_delay: int = Form(30),
    max_delay: int = Form(60),
    cycle_delay_seconds: int = Form(120)
):
    if daily_limit < 0 or min_delay < 0 or max_delay < 0 or cycle_delay_seconds < 0:
        raise HTTPException(status_code=400, detail="Values cannot be negative.")
    if min_delay > max_delay:
        raise HTTPException(status_code=400, detail="min_delay cannot be greater than max_delay.")
    await database.update_settings(
        template=message_template,
        template_2=message_template_2,
        template_3=message_template_3,
        broadcast_mode=max(1, min(3, broadcast_mode)),
        limit=daily_limit,
        min_delay=min_delay,
        max_delay=max_delay,
        cycle_delay=cycle_delay_seconds
    )
    return RedirectResponse(url="/config", status_code=303)

async def run_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
