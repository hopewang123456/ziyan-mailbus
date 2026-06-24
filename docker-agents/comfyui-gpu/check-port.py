import socket
s = socket.socket()
code = s.connect_ex(("127.0.0.1", 8188))
print("connect", code)
s.close()
