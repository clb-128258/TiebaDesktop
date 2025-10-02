# AES 加密算法实现
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64


def decode(item: str, key: str):
    # 解码解密
    if not key:
        return item
    elif not item:
        return ''
    iv = b'vgdfgbdfgbfghsi9'
    aes = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv)
    en_text = unpad(aes.decrypt(base64.b64decode(item.encode('utf-8'))), AES.block_size)  # 解密内容
    return en_text.decode('utf-8')


def encode(item: str, key: str):
    # 编码加密
    if not key:
        return item
    elif not item:
        return ''
    iv = b'vgdfgbdfgbfghsi9'
    aes = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv)
    en_text = aes.encrypt(pad(item.encode('utf-8'), AES.block_size))  # 加密明文
    return base64.b64encode(en_text).decode('utf-8')  # 转换成base64之后编码成字符串
