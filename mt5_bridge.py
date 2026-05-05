import MetaTrader5 as mt5
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.request
from gui import launch_gui

config = {}
httpd = None

def load_config():
    global config
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}
    return config

def save_config(new_config):
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(new_config, f, indent=2)

def send_whatsapp_message(message):
    group_id = config.get("WHATSAPP_GROUP_ID", "120363426979957217@g.us")
    url = "https://deswa.io7.my/api/external/send-message"
    data = json.dumps({"number": group_id, "message": message}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print("WhatsApp Error:", e)

def connect_mt5():
    MT5_LOGIN = int(config.get("MT5_LOGIN", 1610080967))
    MT5_PASSWORD = config.get("MT5_PASSWORD", "4U0*kdee")
    MT5_SERVER = config.get("MT5_SERVER", "STARTRADERFinancial-Demo")
    MT5_PATH = config.get("MT5_PATH", "")

    if MT5_PATH and os.path.exists(MT5_PATH):
        success = mt5.initialize(MT5_PATH, timeout=10000)
    else:
        success = mt5.initialize(timeout=10000)

    if not success:
        print("initialize() failed, error code =", mt5.last_error())
        if config.get("NOTIFY_ERRORS", True):
            send_whatsapp_message(f'❌ MT5 Bridge Initialization Failed')
        return False

    authorized = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    if authorized:
        print(f"Connected to MT5 account #{MT5_LOGIN}")
        if config.get("NOTIFY_MT5_INIT", True):
            send_whatsapp_message(f'🟢 MT5 Bridge Connected to #{MT5_LOGIN}')
        return True
    else:
        print(f"Failed to connect to account #{MT5_LOGIN}, error code: {mt5.last_error()}")
        if config.get("NOTIFY_ERRORS", True):
            send_whatsapp_message(f'❌ MT5 Bridge Failed to connect to #{MT5_LOGIN}')
        return False

def get_filling_type(symbol):
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return mt5.ORDER_FILLING_IOC
    
    if symbol_info.filling_mode == 1:
        return mt5.ORDER_FILLING_FOK
    elif symbol_info.filling_mode == 2:
        return mt5.ORDER_FILLING_IOC
    else:
        return mt5.ORDER_FILLING_IOC

def execute_trade(action, symbol, lot_size=0.01):
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        if config.get("NOTIFY_ERRORS", True):
            send_whatsapp_message(f'❌ MT5 Trade Error: Symbol {symbol} not found in MT5')
        return {"error": f"Symbol {symbol} not found in MT5"}

    if not symbol_info.visible:
        if not mt5.symbol_select(symbol, True):
            if config.get("NOTIFY_ERRORS", True):
                send_whatsapp_message(f'❌ MT5 Trade Error: Failed to select symbol {symbol}')
            return {"error": f"Failed to select symbol {symbol}"}

    if config.get("REVERSE_TRADING", False):
        if action == "BUY":
            action = "SELL"
        elif action == "SELL":
            action = "BUY"

    order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
    price = mt5.symbol_info_tick(symbol).ask if action == "BUY" else mt5.symbol_info_tick(symbol).bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot_size),
        "type": order_type,
        "price": price,
        "deviation": 20,
        "magic": 1001,
        "comment": "Node Scraper",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_type(symbol),
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        if config.get("NOTIFY_ERRORS", True):
            send_whatsapp_message(f'❌ MT5 Trade Error: {result.comment}')
        return {"error": f"Order failed, retcode={result.retcode}, comment={result.comment}"}

    if config.get("NOTIFY_MT5_TRADE", True):
        send_whatsapp_message(f'✅ MT5 Trade Executed: {action} {lot_size} {symbol}')
    return {"success": True, "order": result.order}

def close_all_positions(symbol=None):
    positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
    if positions is None or len(positions) == 0:
        return {"message": "No positions to close"}

    results = []
    for pos in positions:
        order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(pos.symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pos.symbol).ask
        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": order_type,
            "position": pos.ticket,
            "price": price,
            "deviation": 20,
            "magic": 1001,
            "comment": "Close Position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": get_filling_type(pos.symbol),
        }
        res = mt5.order_send(close_request)
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            if config.get("NOTIFY_MT5_TRADE", True):
                send_whatsapp_message(f'✅ MT5 Trade Closed: {pos.ticket}')
        results.append({"ticket": pos.ticket, "retcode": res.retcode, "comment": res.comment})
    
    return {"results": results}

def close_specific_ticket(ticket):
    positions = mt5.positions_get(ticket=ticket)
    if positions is None or len(positions) == 0:
        if config.get("NOTIFY_ERRORS", True):
            send_whatsapp_message(f'❌ MT5 Close Error: Ticket {ticket} not found (Already closed?)')
        return {"error": f"Position with ticket {ticket} not found"}

    pos = positions[0]
    order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = mt5.symbol_info_tick(pos.symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pos.symbol).ask
    
    close_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": order_type,
        "position": pos.ticket,
        "price": price,
        "deviation": 20,
        "magic": 1001,
        "comment": "Close specific ticket",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_type(pos.symbol),
    }
    res = mt5.order_send(close_request)
    if res.retcode != mt5.TRADE_RETCODE_DONE:
        if config.get("NOTIFY_ERRORS", True):
            send_whatsapp_message(f'❌ MT5 Close Ticket Error: {res.comment}')
        return {"error": f"Failed to close ticket {ticket}, retcode={res.retcode}, comment={res.comment}"}
    
    if config.get("NOTIFY_MT5_TRADE", True):
        send_whatsapp_message(f'✅ MT5 Ticket Closed: {pos.ticket}')
    return {"success": True, "ticket": pos.ticket}

class RequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            action = data.get('action')
            symbol = data.get('symbol', 'XAUUSD+')
            lot_size = data.get('size', 0.01)
            ticket = data.get('ticket')

            print(f"-> Received Signal: {action} {lot_size} {symbol} (Ticket: {ticket})")

            if action == "CLOSE":
                result = close_all_positions(symbol)
            elif action == "CLOSE_TICKET":
                if ticket is None:
                    result = {"error": "Missing ticket number for CLOSE_TICKET"}
                else:
                    result = close_specific_ticket(ticket)
            else:
                result = execute_trade(action, symbol, lot_size)

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode('utf-8'))
            print(f"<- Response: {result}")
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

    def log_message(self, format, *args):
        pass

def run_server_thread(port):
    global httpd
    if not connect_mt5():
        print("Could not start MT5 bridge due to connection error.")
        return
    
    server_address = ('127.0.0.1', port)
    httpd = HTTPServer(server_address, RequestHandler)
    print(f"MT5 Bridge is running on http://127.0.0.1:{port}")
    try:
        httpd.serve_forever()
    except Exception:
        pass
    finally:
        mt5.shutdown()

if __name__ == "__main__":
    load_config()
    # Launch GUI and pass in the callback to start the background server thread
    launch_gui(config, save_config, lambda: threading.Thread(target=run_server_thread, args=(5000,), daemon=True).start())
