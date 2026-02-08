"""本地缓存文件管理器"""
import consts
from publics import request_mgr
import requests
import os
import hashlib


def get_md5_icon(md5: str) -> bytes:
    """
    通过MD5值获取缓存图像（如吧头像，网页图标等）

    Args:
        md5 (str): md5值
    Return:
        图像字节数据，如本地找不到则返回空数据
    """
    local_path = f'{consts.datapath}/image_caches/md5_icon_{md5}'
    if not os.path.isfile(local_path):
        return b''
    with open(local_path, 'rb') as file:
        bytesdata = file.read()
        return bytesdata


def save_md5_ico_from_bin(bin_data: bytes) -> str:
    """
    从字节数据直接保存md5缓存图像

    Args:
        bin_data (bytes): 原图像字节数据
    Return:
        md5值
    """
    md5_value = hashlib.md5(bin_data).hexdigest()
    local_path = f'{consts.datapath}/image_caches/md5_icon_{md5_value}'
    if not os.path.isfile(local_path):
        with open(local_path, 'wb') as file:
            file.write(bin_data)

    return md5_value


def save_md5_ico(link_str: str) -> str:
    """
    下载md5缓存图像

    Args:
        link_str (str): 原图像链接
    Return:
        md5值
    """
    response = requests.get(link_str, headers=request_mgr.header)
    bytes_data = response.content
    if bytes_data and response.status_code == 200:
        return save_md5_ico_from_bin(bytes_data)


def get_bd_hash_img(bd_hash: str, original=False) -> bytes:
    """
    通过百度hash从本地缓存获取图像

    Args:
        bd_hash (str): 百度图床hash
        original (bool): 是否获取原图
    Return:
        图像字节数据
    """
    local_path = f'{consts.datapath}/image_caches/bd_hash_img{"_original_size" if original else ""}_{bd_hash}.jpg'
    if not os.path.isfile(local_path):
        return save_bd_hash_img(bd_hash, original)
    with open(local_path, 'rb') as file:
        bytesdata = file.read()
        return bytesdata


def save_bd_hash_img(bd_hash: str, original=False) -> bytes:
    """
    从百度hash下载图像

    Args:
        bd_hash (str): 百度图床hash
        original (bool): 是否下载原图
    Return:
        图像字节数据
    """
    head_url = f'http://imgsrc.baidu.com/forum/{"pic/item" if original else "w=720;q=60;g=0/sign=__"}/{bd_hash}.jpg'
    ex_header = request_mgr.header
    ex_header['Referer'] = 'tieba.baidu.com'

    response = requests.get(head_url, headers=ex_header)
    bytes_data = response.content
    if bytes_data and response.status_code == 200:
        local_path = f'{consts.datapath}/image_caches/bd_hash_img{"_original_size" if original else ""}_{bd_hash}.jpg'
        with open(local_path, 'wb') as file:
            file.write(bytes_data)

        return bytes_data


def get_portrait(portrait: str) -> bytes:
    local_path = f'{consts.datapath}/image_caches/portrait_{portrait}.jpg'
    if not os.path.isfile(local_path):
        save_portrait(portrait)
    with open(local_path, 'rb') as file:
        bytesdata = file.read()
        return bytesdata


def save_portrait(portrait: str):
    head_url = f'http://tb.himg.baidu.com/sys/portraith/item/{portrait}'
    response = requests.get(head_url, headers=request_mgr.header)
    bytes_data = response.content
    if bytes_data and response.status_code == 200:
        local_path = f'{consts.datapath}/image_caches/portrait_{portrait}.jpg'
        with open(local_path, 'wb') as file:
            file.write(bytes_data)
        return bytes_data
