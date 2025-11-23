"""该脚本用于将protobuf定义文件转为python文件，需要protoc"""
import os

PROTOC_PATH = 'D:\\protoc\\bin\\protoc.exe'  # 请修改为你电脑上 protoc 的路径
FINAL_PY_PATH = './../..'
PROTO_DEFINE_PATH = './proto'


def generate_python(files_list):
    file_str = ''
    for i in files_list:
        file_str += i + ' '
    file_str = file_str[0:-1]

    shell = f'{PROTOC_PATH} --proto_path=. --python_out={FINAL_PY_PATH} {file_str}'
    print(shell)
    os.system(shell)

flist = []
for i in os.listdir(PROTO_DEFINE_PATH):
    api_dir = f'{PROTO_DEFINE_PATH}/' + i
    if os.path.isdir(api_dir):
        for j in os.listdir(api_dir):
            flist.append(api_dir + '/' + j)
    else:
        flist.append(api_dir)
generate_python(flist)