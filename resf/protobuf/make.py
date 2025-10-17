"""该脚本用于将protobuf定义文件转为python文件，需要protoc"""
import os

PROTOC_PATH = 'D:\\protoc\\bin\\protoc.exe'  # 请修改为你电脑上 protoc 的路径
FINAL_PY_PATH = '../../proto'
PROTO_DEFINE_PATH = './proto'


def generate_python(files_list):
    file_str = ''
    for i in files_list:
        file_str += i + ' '
    file_str = file_str[0:-1]

    shell = f'{PROTOC_PATH} --proto_path={PROTO_DEFINE_PATH} --python_out={FINAL_PY_PATH} {file_str}'
    print(shell)
    os.system(shell)


for i in os.listdir(PROTO_DEFINE_PATH):
    api_dir = f'{PROTO_DEFINE_PATH}/' + i
    if os.path.isdir(api_dir):
        flist = []
        for j in os.listdir(api_dir):
            flist.append(api_dir + '/' + j)
        generate_python(flist)
    else:
        generate_python([api_dir])
