# Telnet-like Server and Client

This project provides a custom telnet-like server and client implementation in Python. It allows users to connect to a remote server, browse its filesystem, execute commands, and transfer files. The connection uses a custom JSON-based chunked protocol to gracefully handle operations and large file transfers.

## Features
- **Cross-Platform**: Works on Windows, MacOS, and Linux without needing any OS-specific dependencies. Operations like `ls`, `pwd`, `cd`, and `cat` are implemented through Python's built-in `os` module for guaranteed cross-platform compatibility.
- **File Browsing**: Browse directories using `ls`, change directories with `cd`, print the current working directory with `pwd`, and read files securely with `cat`.
- **Remote Execution**: Run any native shell command with `exec <command>`. The output (stdout and stderr) is returned to the client and printed directly to your console.
- **File Transfers**: Upload and download files smoothly using `upload` and `download` commands. Uses chunking to prevent maxing out memory when transferring massive files. 

## Requirements
- Python 3.6 or later.
- No external module installations required (only standard libraries are used).

## Usage

### 1. Starting the Server
Run the server script. By default, it listens on all interfaces (`0.0.0.0`) on port `2323`.
```bash
python server.py
```
To specify a custom port:
```bash
python server.py 8080
```

### 2. Starting the Client
Run the client script to connect to the server. By default, it tries to connect to `127.0.0.1` on port `2323`.
```bash
python client.py
```
To specify a custom host and port:
```bash
# Connect to IP 192.168.1.100 on port 2323
python client.py 192.168.1.100

# Connect to IP 192.168.1.100 on port 8080
python client.py 192.168.1.100 8080
```

### 3. Supported Client Commands
Once connected, you will see a `remote>` prompt. You can use any of the following commands:
- `pwd`: Print the working directory of the server.
- `ls [directory]`: List files and folders in the current (or specified) directory.
- `cd <directory>`: Change the server's working directory.
- `cat <file>`: Read and display the contents of a text file inside the server.
- `exec <command>`: Execute a system command directly on the remote shell and return its stdout and stderr to you. Examples: 
  - On Linux/Mac: `exec ls -la`
  - On Windows: `exec dir`
- `upload <local_path> <remote_path>`: Upload a local file to the remote server.
- `download <remote_path> <local_path>`: Download a remote file to your local machine.
- `exit` or `quit`: Disconnect gracefully and close the client.
