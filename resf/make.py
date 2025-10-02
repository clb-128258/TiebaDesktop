"""该脚本用于将qt设计文件转为python文件，需要安装pyqt5_tools，如用不上该工具可以不用安装"""
import os
import hashlib
import json

PYUIC_PATH = 'D:\\pyqt_venvs\\qt5\\Scripts\\pyuic5'  # 请修改为你电脑上 pyuic5 的路径

if os.path.isfile('change_index.json'):
    with open('change_index.json', "rt") as f:
        index = json.loads(f.read())
else:
    index = {}
    with open('change_index.json', "wt") as f:
        f.write('{}')

for i in os.listdir():
    houzhui = '.ui'
    if i.endswith(houzhui):
        pyname = i.split('.')[0] + '.py'
        # 读取md5值
        with open(i, "rb") as f:
            file_content = f.read()
        md5_hash = hashlib.md5(file_content).hexdigest()

        if index.get(i) != md5_hash:
            shell = f'{PYUIC_PATH} -o \"../ui/{pyname}\" \"{os.getcwd()}\\{i}\"'
            print(shell)
            os.system(shell)
            index[i] = md5_hash

with open('change_index.json', "wt") as f:
    f.write(json.dumps(index))
