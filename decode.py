import base64

base64_str = "eyJkZXRhaWwiOiJhcmNoaXZlX21lc3NhZ2XkuI3lrZjlnKgiLCJjb2RlIjo0MDR9"
decoded = base64.b64decode(base64_str)
print("解码后的内容:", decoded)
print("UTF-8解码:", decoded.decode('utf-8'))