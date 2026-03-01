import socket
import struct
import json
import base64
import os
import sys
import shlex
import subprocess

try:
    import readline
except ImportError:
    readline = None

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
        
    filesize = os.path.getsize(local_path)
    resp = send_and_recv(sock, {"cmd": "upload_start", "args": [remote_path]})
    if not resp or resp.get("status") != "ok":
        print("Error:", resp.get("error") if resp else "Connection lost")
        return
    
    uploaded = 0
    try:
        with open(local_path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                
                b64chunk = base64.b64encode(chunk).decode('ascii')
                resp = send_and_recv(sock, {"cmd": "upload_chunk", "data": b64chunk})
                if not resp or resp.get("status") != "ok":
                    print("\nError uploading chunk:", resp.get("error") if resp else "Connection lost")
                    return
                
                uploaded += len(chunk)
                if filesize > 0:
                    percent = min(100, int((uploaded / filesize) * 100))
                    bar = '#' * (percent // 2) + '-' * (50 - (percent // 2))
                    sys.stdout.write(f"\r[{bar}] {percent}% ({uploaded}/{filesize} bytes) ")
                    sys.stdout.flush()
                else:
                    sys.stdout.write(f"\rUploaded {uploaded} bytes ")
                    sys.stdout.flush()
                    
        resp = send_and_recv(sock, {"cmd": "upload_end"})
        if resp:
            print("\n" + resp.get("output", "Done"))
    except Exception as e:
        print(f"\nFailed to read local file: {e}")

def make_completer(sock):
    def completer(text, state):
        if state == 0:
            line = readline.get_line_buffer()
            if " " not in line:
                cmds = ["ls", "cat", "cd", "pwd", "exec", "upload", "download", "exit", "quit", "cpwd", "ccd", "cls", "ccat", "cexec"]
                completer.matches = sorted([c + " " for c in cmds if c.startswith(text)])
            else:
                parts = line.split(maxsplit=1)
                cmd = parts[0]
                
                words = line.split()
                if cmd in ["cpwd", "ccd", "cls", "ccat"]:
                    is_local = True
                elif cmd == "upload":
                    is_local = (len(words) == 1 and line.endswith(" ")) or (len(words) == 2 and not line.endswith(" "))
                elif cmd == "download":
                    is_local = not ((len(words) == 1 and line.endswith(" ")) or (len(words) == 2 and not line.endswith(" ")))
                else:
                    is_local = False
                    
                if is_local:
                    norm_prefix = text.replace('\\', '/')
                    dir_part = os.path.dirname(norm_prefix)
                    base_prefix = os.path.basename(norm_prefix)
                    target_dir = dir_part or "."
                    
                    completer.matches = []
                    if os.path.isdir(target_dir):
                        try:
                            for item in os.listdir(target_dir):
                                if item.startswith(base_prefix):
                                    item_path = os.path.join(target_dir, item)
                                    match = f"{dir_part}/{item}" if dir_part else item
                                    if os.path.isdir(item_path):
                                        completer.matches.append(match + "/")
                                    else:
                                        completer.matches.append(match)
                        except Exception:
                            pass
                    completer.matches.sort()
                else:
                    resp = send_and_recv(sock, {"cmd": "complete", "args": [text]})
                    if resp and resp.get("status") == "ok":
                        completer.matches = resp.get("matches", [])
                    else:
                        completer.matches = []
                        
        if state < len(completer.matches):
            return completer.matches[state]
        return None

    completer.matches = []
    return completer

def handle_download(sock, remote_path, local_path):
    resp = send_and_recv(sock, {"cmd": "download_req", "args": [remote_path]})
    if not resp or resp.get("status") != "ok":
        print("Error:", resp.get("error") if resp else "Connection lost")
        return
        
    filesize = resp.get("filesize", 0)
    downloaded = 0
    try:
        with open(local_path, "wb") as f:
            while True:
                resp = send_and_recv(sock, {"cmd": "download_chunk"})
                if not resp:
                    print("\nConnection lost")
                    return
                if resp.get("status") == "done":
                    break
                elif resp.get("status") != "ok":
                    print("\nError downloading chunk:", resp.get("error"))
                    return
                
                chunk = base64.b64decode(resp.get("data"))
                f.write(chunk)
                downloaded += len(chunk)
                if filesize > 0:
                    percent = min(100, int((downloaded / filesize) * 100))
                    bar = '#' * (percent // 2) + '-' * (50 - (percent // 2))
                    sys.stdout.write(f"\r[{bar}] {percent}% ({downloaded}/{filesize} bytes) ")
                    sys.stdout.flush()
                else:
                    sys.stdout.write(f"\rDownloaded {downloaded} bytes ")
                    sys.stdout.flush()
                    
        print("\nDownload complete.")
    except Exception as e:
        print("\nFailed to save local file:", str(e))

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
    
    if readline is not None:
        try:
            delims = readline.get_completer_delims()
            delims = delims.replace('/', '').replace('\\', '')
            readline.set_completer_delims(delims)
            readline.set_completer(make_completer(sock))
            if sys.platform == 'darwin':
                readline.parse_and_bind("bind ^I rl_complete")
            else:
                readline.parse_and_bind("tab: complete")
        except Exception as e:
            print(f"Warning: Tab completion setup failed: {e}")
    else:
        print("Note: 'readline' module not found. Tab completion will not be available.")
        if os.name == 'nt':
            print("To enable tab completion on Windows, run: pip install pyreadline3")
            
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
        elif user_input.startswith("cexec "):
            cmd = "cexec"
            command_str = user_input[6:].strip()
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
            
        if cmd == "cpwd":
            print(os.getcwd())
            continue
            
        if cmd == "ccd":
            if not args:
                print("ccd requires a directory")
            else:
                try:
                    os.chdir(args[0])
                except Exception as e:
                    print(f"Error: {e}")
            continue
            
        if cmd == "cls":
            target = os.getcwd()
            if args:
                target = args[0]
            if os.path.isdir(target):
                items = os.listdir(target)
                res = []
                for item in items:
                    item_path = os.path.join(target, item)
                    if os.path.isdir(item_path):
                        res.append(f"{item}/")
                    else:
                        res.append(item)
                print("\n".join(res))
            else:
                print("Directory not found")
            continue
            
        if cmd == "ccat":
            if not args:
                print("ccat requires a file")
            else:
                target = args[0]
                if os.path.isfile(target):
                    try:
                        with open(target, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                            print(content, end="")
                            if not content.endswith("\n"):
                                print()
                    except Exception as e:
                        print(f"Error: {e}")
                else:
                    print("File not found")
            continue
            
        if cmd == "cexec":
            if not args:
                print("cexec requires a command")
            else:
                command = args[0] if len(args) == 1 else " ".join(args)
                try:
                    proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
                    stdout, _ = proc.communicate()
                    print(stdout, end="")
                    if not stdout.endswith("\n"):
                        print()
                except Exception as e:
                    print(f"Error: {e}")
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
            print("Client supported commands: ls, cat, cd, pwd, exec <command>, upload <local> <remote>, download <remote> <local>, cpwd, cls, ccd, ccat, cexec <command>, exit")
            
    sock.close()

if __name__ == "__main__":
    main()
