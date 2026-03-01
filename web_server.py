import asyncio
import websockets
import json
import os
import subprocess
import threading
import http.server
import socketserver
import shlex

HTTP_PORT = 8080
WS_PORT = 8081

class WebClientHandler:
    def __init__(self, ws):
        self.ws = ws
        self.cwd = os.getcwd()
        self.upload_file = None
        self.download_target = None

    def get_abs_path(self, path):
        if os.path.isabs(path):
            return path
        return os.path.abspath(os.path.join(self.cwd, path))

    async def handle_cmd(self, line):
        line = line.strip()
        if not line:
            return {"type": "output", "data": ""}
            
        try:
            if os.name == 'nt':
                parts = shlex.split(line, posix=False)
                parts = [p.strip('"\'') for p in parts]
            else:
                parts = shlex.split(line)
        except ValueError as e:
            return {"type": "output", "data": f"Error parsing command: {e}\r\n"}
            
        if not parts:
            return {"type": "output", "data": ""}
            
        cmd = parts[0]
        args = parts[1:]

        try:
            if cmd == "pwd":
                return {"type": "output", "data": self.cwd + "\r\n"}
            elif cmd == "cd":
                if not args:
                    return {"type": "output", "data": "cd requires a directory\r\n"}
                target = self.get_abs_path(args[0])
                if os.path.isdir(target):
                    self.cwd = target
                    return {"type": "output", "data": ""}
                else:
                    return {"type": "output", "data": "Directory not found\r\n"}
            elif cmd == "ls":
                target = self.cwd
                if args:
                    target = self.get_abs_path(args[0])
                if os.path.isdir(target):
                    items = os.listdir(target)
                    res = []
                    for item in items:
                        item_path = os.path.join(target, item)
                        if os.path.isdir(item_path):
                            res.append(f"\033[1;36m{item}/\033[0m")
                        else:
                            res.append(item)
                    return {"type": "output", "data": ("\r\n".join(res) + "\r\n" if res else "")}
                else:
                    return {"type": "output", "data": "Directory not found\r\n"}
            elif cmd == "cat":
                if not args:
                    return {"type": "output", "data": "cat requires a file\r\n"}
                target = self.get_abs_path(args[0])
                if os.path.isfile(target):
                    with open(target, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                        return {"type": "output", "data": content.replace('\n', '\r\n') + "\r\n"}
                else:
                    return {"type": "output", "data": "File not found\r\n"}
            elif cmd == "exec":
                if not args:
                    return {"type": "output", "data": "exec requires a command\r\n"}
                command = args[0] if len(args) == 1 else " ".join(args)
                proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=self.cwd, text=True, encoding="utf-8", errors="replace")
                stdout, _ = proc.communicate()
                return {"type": "output", "data": stdout.replace('\n', '\r\n') + "\r\n"}
            elif cmd == "clear":
                return {"type": "output", "data": "\033[2J\033[H"}
            elif cmd == "upload":
                if not args:
                    return {"type": "output", "data": "upload requires a path\r\n"}
                return {"type": "trigger_upload", "path": args[0]}
            elif cmd == "download":
                if not args:
                    return {"type": "output", "data": "download requires a file\r\n"}
                return {"type": "trigger_download", "path": args[0], "local_name": args[1] if len(args) > 1 else ""}
            elif cmd == "complete":
                prefix = args[0] if args else ""
                norm_prefix = prefix.replace('\\', '/')
                dir_part = os.path.dirname(norm_prefix)
                base_prefix = os.path.basename(norm_prefix)
                
                target_dir = self.get_abs_path(dir_part or ".")
                
                matches = []
                if os.path.isdir(target_dir):
                    try:
                        for item in os.listdir(target_dir):
                            if item.startswith(base_prefix):
                                item_path = os.path.join(target_dir, item)
                                match = f"{dir_part}/{item}" if dir_part else item
                                if os.path.isdir(item_path):
                                    matches.append(match + "/")
                                else:
                                    matches.append(match)
                    except Exception:
                        pass
                return {"type": "completion", "matches": sorted(matches)}
            else:
                return {"type": "output", "data": f"Unknown command {cmd}. Supported: ls, cat, cd, pwd, exec, clear, upload, download\r\n"}
        except Exception as e:
            return {"type": "output", "data": f"Error: {str(e)}\r\n"}

    async def handle_rpc(self, data):
        cmd = data.get("command")
        args = data.get("args", [])
        
        try:
            if cmd == "upload_start":
                target = self.get_abs_path(args[0])
                self.upload_file = open(target, "wb")
                return {"type": "rpc_response", "status": "ok"}
            elif cmd == "upload_chunk":
                if self.upload_file:
                    import base64
                    chunk = base64.b64decode(data.get("data", ""))
                    self.upload_file.write(chunk)
                    return {"type": "rpc_response", "status": "ok"}
                return {"type": "rpc_response", "status": "error", "error": "No upload in progress"}
            elif cmd == "upload_end":
                if self.upload_file:
                    self.upload_file.close()
                    self.upload_file = None
                    return {"type": "rpc_response", "status": "ok"}
                return {"type": "rpc_response", "status": "error", "error": "No upload in progress"}
            elif cmd == "download_req":
                target = self.get_abs_path(args[0])
                if os.path.isfile(target):
                    self.download_target = open(target, "rb")
                    size = os.path.getsize(target)
                    return {"type": "rpc_response", "status": "ok", "filesize": size}
                return {"type": "rpc_response", "status": "error", "error": "File not found"}
            elif cmd == "download_chunk":
                if self.download_target:
                    import base64
                    chunk = self.download_target.read(128 * 1024)
                    if not chunk:
                        self.download_target.close()
                        self.download_target = None
                        return {"type": "rpc_response", "status": "done"}
                    b64content = base64.b64encode(chunk).decode('ascii')
                    return {"type": "rpc_response", "status": "ok", "data": b64content}
                return {"type": "rpc_response", "status": "error", "error": "No download in progress"}
        except Exception as e:
            return {"type": "rpc_response", "status": "error", "error": str(e)}

async def ws_handler(websocket, *args, **kwargs):
    client = WebClientHandler(websocket)
    prompt = f"\r\n\033[1;32mweb-remote\033[0m:\033[1;34m{client.cwd}\033[0m$ "
    await websocket.send(json.dumps({"type": "output", "data": prompt}))
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get("type") == "cmd":
                    line = data.get("command", "")
                    prompt_needed = True
                    
                    output_dict = await client.handle_cmd(line)
                    if output_dict:
                        if output_dict.get("type") in ("completion", "trigger_upload", "trigger_download"):
                            await websocket.send(json.dumps(output_dict))
                            prompt_needed = False
                        else:
                            out_data = output_dict.get("data", "")
                            prompt = f"\r\n\033[1;32mweb-remote\033[0m:\033[1;34m{client.cwd}\033[0m$ "
                            if out_data == "\033[2J\033[H":
                                await websocket.send(json.dumps({"type": "output", "data": out_data + prompt.lstrip("\r\n")}))
                            else:
                                await websocket.send(json.dumps({"type": "output", "data": out_data + prompt}))
                            prompt_needed = False
                        
                    if prompt_needed:
                        prompt = f"\r\n\033[1;32mweb-remote\033[0m:\033[1;34m{client.cwd}\033[0m$ "
                        await websocket.send(json.dumps({"type": "output", "data": prompt}))
                elif data.get("type") == "rpc":
                    resp = await client.handle_rpc(data)
                    await websocket.send(json.dumps(resp))
            except json.JSONDecodeError:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if client.upload_file:
            client.upload_file.close()
        if client.download_target:
            client.download_target.close()

def serve_http():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    class CustomHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass 
    with socketserver.TCPServer(("", HTTP_PORT), CustomHandler) as httpd:
        print(f"HTTP Server serving at http://localhost:{HTTP_PORT}/web_client.html")
        httpd.serve_forever()

async def serve_ws():
    print(f"WebSocket Server listening on ws://localhost:{WS_PORT}")
    async with websockets.serve(ws_handler, "0.0.0.0", WS_PORT):
        await asyncio.Future()

def main():
    http_thread = threading.Thread(target=serve_http, daemon=True)
    http_thread.start()
    asyncio.run(serve_ws())

if __name__ == "__main__":
    main()
