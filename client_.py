import socket
import struct
import json
import base64
import os
import sys
import shlex

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

def send_and_recv(sock, msg):
    send_msg(sock, msg)
    return recv_msg(sock)

def handle_upload(sock, local_path, remote_path):
    if not os.path.isfile(local_path):
        print("Local file not found.")
        return
    resp = send_and_recv(sock, {"cmd": "upload_start", "args": [remote_path]})
    if not resp or resp.get("status") != "ok":
        print("Error:", resp.get("error") if resp else "Connection lost")
        return
    
    try:
        with open(local_path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                b64chunk = base64.b64encode(chunk).decode('ascii')
                resp = send_and_recv(sock, {"cmd": "upload_chunk", "data": b64chunk})
                if not resp or resp.get("status") != "ok":
                    print("Error uploading chunk:", resp.get("error") if resp else "Connection lost")
                    return
                    
        resp = send_and_recv(sock, {"cmd": "upload_end"})
        if resp:
            print(resp.get("output", "Done"))
    except Exception as e:
        print(f"Failed to read local file: {e}")

def handle_download(sock, remote_path, local_path):
    resp = send_and_recv(sock, {"cmd": "download_req", "args": [remote_path]})
    if not resp or resp.get("status") != "ok":
        print("Error:", resp.get("error") if resp else "Connection lost")
        return
        
    try:
        with open(local_path, "wb") as f:
            while True:
                resp = send_and_recv(sock, {"cmd": "download_chunk"})
                if not resp:
                    print("Connection lost")
                    return
                if resp.get("status") == "done":
                    break
                elif resp.get("status") != "ok":
                    print("Error downloading chunk:", resp.get("error"))
                    return
                chunk = base64.b64decode(resp.get("data"))
                f.write(chunk)
        print("Download complete.")
    except Exception as e:
        print("Failed to save local file:", str(e))

def main():
    host = "127.0.0.1"
    port = 2323
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
        
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
    except Exception as e:
        print(f"Failed to connect to {host}:{port}. Error: {e}")
        return
        
    print(f"Connected to {host}:{port}")
    
    while True:
        try:
            user_input = input("remote> ")
        except (EOFError, KeyboardInterrupt):
            print("\nDisconnecting...")
            break
            
        user_input = user_input.strip()
        if not user_input:
            continue
            
        if user_input.startswith("exec "):
            cmd = "exec"
            command_str = user_input[5:].strip()
            args = [command_str]
        else:
            try:
                if os.name == 'nt':
                    parts = shlex.split(user_input, posix=False)
                    parts = [p.strip('"\'') for p in parts]
                else:
                    parts = shlex.split(user_input)
            except ValueError as e:
                print(f"Error parsing command: {e}")
                continue
                
            if not parts:
                continue
                
            cmd = parts[0]
            args = parts[1:]
        
        if cmd in ("exit", "quit"):
            break
            
        if cmd == "upload":
            if len(args) < 2:
                print("Usage: upload <local_file> <remote_path>")
                continue
            handle_upload(sock, args[0], args[1])
            continue
            
        if cmd == "download":
            if len(args) < 2:
                print("Usage: download <remote_file> <local_path>")
                continue
            handle_download(sock, args[0], args[1])
            continue
            
        if cmd in ("ls", "cat", "cd", "pwd", "exec"):
            resp = send_and_recv(sock, {"cmd": cmd, "args": args})
            if resp:
                if resp.get("status") == "ok":
                    out = resp.get("output", "")
                    if out:
                        print(out)
                else:
                    print("Error:", resp.get("error"))
            else:
                print("Connection lost.")
                break
        else:
            print("Client supported commands: ls, cat, cd, pwd, exec <command>, upload <local> <remote>, download <remote> <local>, exit")
            
    sock.close()

if __name__ == "__main__":
    main()
