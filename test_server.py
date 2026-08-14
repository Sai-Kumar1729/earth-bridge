import socket
import sys
import traceback

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', 8085))
    s.listen(5)
    print("Listening on", s.getsockname(), file=sys.stderr)
    sys.stderr.flush()

    while True:
        try:
            print("Waiting for accept...", file=sys.stderr)
            sys.stderr.flush()
            conn, addr = s.accept()
            print("Connection from", addr, file=sys.stderr)
            sys.stderr.flush()
            request = conn.recv(1024)
            response = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nHello World"
            conn.send(response)
            conn.close()
        except Exception as e:
            print("Accept error:", e, file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            break
except Exception as e:
    print("Bind error:", e, file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
finally:
    print("Exiting...", file=sys.stderr)
    sys.stderr.flush()