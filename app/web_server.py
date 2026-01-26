from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn
import asyncio
from app import database
import os
from collections import deque

app = FastAPI()

# Setup templates
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')
os.makedirs(TEMPLATES_DIR, exist_ok=True)
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Shared log buffer
log_buffer = deque(maxlen=50)

def add_log(message: str):
    log_buffer.append(message)

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    stats = {}
    stats['total_sent'] = await database.get_stat('total_sent')
    stats['daily_sent'] = await database.get_stat('daily_sent')
    stats['start_date'] = await database.get_stat('start_date')

    chats = await database.get_chats()
    active_chats = sum(1 for c in chats if c['status'] == 'active')
    error_chats = sum(1 for c in chats if c['status'] == 'error')

    settings = await database.get_settings()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "tab": "dashboard",
        "stats": stats,
        "active_chats_count": active_chats,
        "error_chats_count": error_chats,
        "total_chats_count": len(chats),
        "limit": settings.get('daily_limit', 400)
    })

@app.get("/logs", response_class=HTMLResponse)
async def logs(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "tab": "logs",
        "logs": list(log_buffer)
    })

@app.get("/chats", response_class=HTMLResponse)
async def chats(request: Request):
    chat_list = await database.get_chats()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "tab": "chats",
        "chats": chat_list
    })

@app.post("/chats/delete")
async def delete_chat(chat_id: int = Form(...)):
    await database.remove_chat(chat_id)
    return RedirectResponse(url="/chats", status_code=303)

@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    conf = await database.get_settings()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "tab": "config",
        "config": conf
    })

@app.post("/config/update")
async def update_config(message_template: str = Form(...), daily_limit: int = Form(...)):
    await database.update_settings(template=message_template, limit=daily_limit)
    return RedirectResponse(url="/config", status_code=303)

async def run_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=80, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
