import asyncio
from fastapi import WebSocket
import datetime

connected_websockets = set()
main_loop = None
log_history = []
last_log_date = datetime.date.today()

def init_logger_loop(loop):
    global main_loop
    main_loop = loop

def wlog(message: str):
    """Envía el mensaje a la consola y a todos los WebSockets conectados."""
    global last_log_date
    current_date = datetime.date.today()
    
    # Limpieza diaria automática
    if current_date != last_log_date:
        log_history.clear()
        last_log_date = current_date
        msg_clear = f"📅 [Sistema] --- NUEVO DÍA: LOGS LIMPIADOS AUTOMÁTICAMENTE PARA EL {current_date.strftime('%Y-%m-%d')} ---"
        print(msg_clear)
        log_history.append(msg_clear)
        
    print(message)
    log_history.append(message)
    if len(log_history) > 150:
        log_history.pop(0)
    if main_loop and main_loop.is_running():
        asyncio.run_coroutine_threadsafe(_broadcast(message), main_loop)

async def _broadcast(message: str):
    dead = set()
    for ws in connected_websockets:
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)
    for d in dead:
        try:
            connected_websockets.remove(d)
        except: pass

async def connect_ws(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.add(websocket)
    # Enviar historial al cliente recién conectado
    for msg in log_history:
        try:
            await websocket.send_text(msg)
        except Exception:
            break
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        try:
            connected_websockets.remove(websocket)
        except: pass
