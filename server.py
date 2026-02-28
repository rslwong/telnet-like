import socket
import struct
import json
import base64
import os
import subprocess
import threading
import sys

def send_msg(sock, msg_dict):
    data = json.dumps(msg_dict).encode('utf-8')
    sock.sendall(struct.pack(">I", len(data)) + data)

def recv_msg(sock):
    raw_msglen = recvall(sock, 4)
    if not raw_msglen:
        return None
    msglen = struct.unpack(">I", raw_msglen)[0]
    data = recvall(sock, msglen)
    if not data:
        return None
    return json.loads(data.decode('utf-8'))

def recvall(sock, n):
    data = bytearray()
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            return None
        data.extend(packet)
    return data

class ClientHandler(threading.Thread):
    def __init__(self, sock, addr):
        super().__init__()
        self.sock = sock
        self.addr = addr
        self.cwd = os.getcwd()
        self.upload_file = None
        self.download_target = None

    def run(self):
        print(f"Client connected: {self.addr}")
        try:
            while True:
                msg = recv_msg(self.sock)
                if not msg:
                    break
                resp = self.handle_cmd(msg)
                if resp is not None:
                    send_msg(self.sock, resp)
        except Exception as e:
            print(f"Client {self.addr} error: {e}")
        finally:
            if self.upload_file:
                self.upload_file.close()
            if self.download_target:
                self.download_target.close()
            self.sock.close()
            print(f"Client disconnected: {self.addr}")

    def get_abs_path(self, path):
        if os.path.isabs(path):
            return path
        return os.path.abspath(os.path.join(self.cwd, path))

    def handle_cmd(self, msg):
        cmd = msg.get("cmd")
        args = msg.get("args", [])
        
        try:
            if cmd == "pwd":
                return {"status": "ok", "output": self.cwd}
            elif cmd == "cd":
                if not args:
                    return {"status": "error", "error": "cd requires a directory"}
                target = self.get_abs_path(args[0])
                if os.path.isdir(target):
                    self.cwd = target
                    return {"status": "ok", "output": ""}
                else:
                    return {"status": "error", "error": "Directory not found"}
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
                            res.append(f"{item}/")
                        else:
                            res.append(item)
                    return {"status": "ok", "output": "\n".join(res)}
                else:
                    return {"status": "error", "error": "Directory not found"}
            elif cmd == "cat":
                if not args:
                    return {"status": "error", "error": "cat requires a file"}
                target = self.get_abs_path(args[0])
                if os.path.isfile(target):
                    with open(target, "r", encoding="utf-8", errors="replace") as f:
                        return {"status": "ok", "output": f.read()}
                else:
                    return {"status": "error", "error": "File not found"}
            elif cmd == "exec":
                if not args:
                    return {"status": "error", "error": "exec requires a command"}
                command = args[0] if len(args) == 1 else " ".join(args)
                proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=self.cwd, text=True, encoding="utf-8", errors="replace")
                stdout, _ = proc.communicate()
                return {"status": "ok", "output": stdout}
            elif cmd == "upload_start":
                target = self.get_abs_path(args[0])
                self.upload_file = open(target, "wb")
                return {"status": "ok"}
            elif cmd == "upload_chunk":
                if self.upload_file:
                    data = base64.b64decode(msg.get("data", ""))
                    self.upload_file.write(data)
                    return {"status": "ok"}
                return {"status": "error", "error": "No upload in progress"}
            elif cmd == "upload_end":
                if self.upload_file:
                    self.upload_file.close()
                    self.upload_file = None
                    return {"status": "ok", "output": "Upload complete"}
                return {"status": "error", "error": "No upload in progress"}
            elif cmd == "download_req":
                target = self.get_abs_path(args[0])
                if os.path.isfile(target):
                    self.download_target = open(target, "rb")
                    return {"status": "ok"}
                else:
                    return {"status": "error", "error": "File not found"}
            elif cmd == "download_chunk":
                if self.download_target:
                    chunk = self.download_target.read(1024 * 1024)
                    if not chunk:
                        self.download_target.close()
                        self.download_target = None
                        return {"status": "done"}
                    b64content = base64.b64encode(chunk).decode('ascii')
                    return {"status": "ok", "data": b64content}
                return {"status": "error", "error": "No download in progress"}
            else:
                return {"status": "error", "error": f"Unknown command {cmd}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

def main():
    port = 2323
    host = "0.0.0.0"
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((host, port))
        server.listen(5)
        print(f"Telnet-like Server listening on {host}:{port}")
    except Exception as e:
        print(f"Failed to bind on {host}:{port}. Error: {e}")
        return

    try:
        while True:
            client_sock, addr = server.accept()
            handler = ClientHandler(client_sock, addr)
            handler.daemon = True
            handler.start()
    except KeyboardInterrupt:
        print("\nServer shutting down.")
    finally:
        server.close()

if __name__ == "__main__":
    main()
