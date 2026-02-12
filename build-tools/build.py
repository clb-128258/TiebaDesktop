"""
主程序编译脚本

Args:
    -m, --makefile: 指定编译配置文件的路径
Notes:
    makefile 是一个 json 文件，用于指定各种配置选项，具体 json 架构可参考 ./build_config.json 文件\n
    在执行编译脚本前，请先删除本目录下的 work_temp 与 work_out 目录（如果有）\n
    编译执行完后，可以在 work_out 目录下找到生成的发行压缩包与安装程序文件。
"""
import subprocess
import argparse
import json
import os
import shutil
import platform


def get_system_name():
    system_index = {'Windows': 'win',
                    'Linux': 'manylinux',
                    'Darwin': 'macosx',
                    'Java': 'android'}
    cputype_index = {'AMD64': '64',
                     'i386': '32',
                     'x86_64': '64',
                     'x86': '32'}
    systype = system_index.get(platform.system(), 'unknownos')
    cputype = cputype_index.get(platform.machine(), 'unknowncpu')

    return systype + cputype


def load_json(filename):
    """加载json文件"""
    with open(filename, 'rt', encoding='utf-8') as file:
        items = json.loads(file.read())
    return items


def get_cfg_path():
    arg_parser = argparse.ArgumentParser(prog='TiebaDesktop Builder')
    arg_parser.add_argument('-m', '--makefile', required=True,
                            help='set the path of makefile that contains build config')
    args = arg_parser.parse_args()
    return args.makefile


def compile_nsis_pkg(cfg):
    if os.name != 'nt':
        return
    if not cfg['installer_cfg']['build_nsis']:
        return

    print('[compile_nsis_pkg] compiling nsis installer')

    version = cfg['version']['version_string']
    git_hash = cfg['version']['git_last_commit_hash']
    system_name = get_system_name()
    exe_name = f'TiebaDesktop-nsis-installer-{version}-{git_hash}-{system_name}.exe'

    with open('./nsis_script.nsi', 'rt', encoding='gbk') as file:
        nsis_script = file.read()

    nsis_script = nsis_script.replace('[installer_name]', exe_name)
    nsis_script = nsis_script.replace('[verstr]', cfg["version"]['version_string'])

    with open('./_temp_nsis_script.nsi', 'wt', encoding='gbk') as file:
        file.write(nsis_script)

    args = [cfg['installer_cfg']['makensis_path'],
            './_temp_nsis_script.nsi']
    process = subprocess.Popen(args=args, cwd='.')
    process.wait()
    print(f'[compile_nsis_pkg] makensis process finished with exit code {process.returncode}')
    os.remove('./_temp_nsis_script.nsi')


def pack_compressed(cfg):
    print('[pack_compressed] compressing zip package')

    if not os.path.isdir('./work_out'):
        os.mkdir('./work_out')

    version = cfg['version']['version_string']
    git_hash = cfg['version']['git_last_commit_hash']
    system_name = get_system_name()
    zip_name = f'TiebaDesktop-{version}-{git_hash}-{system_name}.zip'
    args = [cfg['sevenzip_path'],
            'a',
            '-tzip',
            '-mx=5',
            './work_out/' + zip_name,
            './work_temp/*', ]
    process = subprocess.Popen(args=args, cwd='.')
    process.wait()
    print(f'[pack_compressed] 7-zip process finished with exit code {process.returncode}')


def cleanup_pyinstaller_file():
    print('[cleanup_pyinstaller_file] running build file cleaner')

    # 清理根目录
    exclude_dirs = ['ui', 'dist', 'binres']
    for file in os.listdir('./work_temp'):
        path = './work_temp/' + file
        if file in exclude_dirs:
            continue

        if os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path)
        print(f'[cleanup_pyinstaller_file] {path} has been deleted')

    # 清理ui目录
    include_dirs = ['__pycache__']
    include_ends = ('.py',)
    for file in os.listdir('./work_temp/ui'):
        path = './work_temp/ui/' + file
        if os.path.isfile(path) and path.endswith(include_ends):
            os.remove(path)
            print(f'[cleanup_pyinstaller_file] file {path} has been deleted')
        elif os.path.isdir(path) and file in include_dirs:
            shutil.rmtree(path)
            print(f'[cleanup_pyinstaller_file] dir {path} has been deleted')

    print(f'[cleanup_pyinstaller_file] processing executable files')
    shutil.copytree('./work_temp/dist/main', './work_temp', dirs_exist_ok=True)
    shutil.rmtree('./work_temp/dist')
    os.remove('./work_temp/binres/.gitignore')
    original_executable_name = 'main.exe' if os.name == 'nt' else 'main'
    new_executable_name = 'TiebaDesktop.exe' if os.name == 'nt' else 'tiebadesktop'
    os.rename(f'./work_temp/{original_executable_name}', f'./work_temp/{new_executable_name}')


def run_pyinstaller(cfg):
    print('[run_pyinstaller] running pyinstaller')

    with open('./windows_version_info.txt', 'rt', encoding='utf-8') as file:
        ver_text = file.read()

    vertuple = '(' + (', '.join(str(i) for i in cfg["version"]["version_array"])) + ')'
    ver_text = ver_text.replace('[vertuple]', vertuple)
    ver_text = ver_text.replace('[verstr]', cfg["version"]['version_string'])

    with open('./_temp_windows_version_info.txt', 'wt', encoding='utf-8') as file:
        file.write(ver_text)

    args = [cfg['py_environ_path'] + r'\Scripts\pyinstaller.exe',
            '-D',
            '-w',
            '--version-file',
            r'.\..\_temp_windows_version_info.txt',
            '-i',
            r'.\ui\tieba_logo_big_single.ico',
            r'.\main.py']
    process = subprocess.Popen(args=args, cwd='./work_temp')
    process.wait()
    print(f'[run_pyinstaller] pyinstaller process finished with exit code {process.returncode}')
    os.remove('./_temp_windows_version_info.txt')
    if process.returncode != 0:
        raise ChildProcessError('pyinstaller process failed!')


def copy_source(cfg):
    print('[copy_source] copying source to temp dir')
    if os.path.isdir('./work_temp'):
        raise FileExistsError('work_temp tree is existing. Make sure the dir does not exist.')
    else:
        shutil.copytree(cfg['src_code_path'], './work_temp')


def main():
    mkfile = get_cfg_path()
    mkfile_config = load_json(mkfile)
    print('[TiebaDesktop Builder] makefile loaded')

    copy_source(mkfile_config)
    run_pyinstaller(mkfile_config)
    cleanup_pyinstaller_file()
    pack_compressed(mkfile_config)
    compile_nsis_pkg(mkfile_config)

    print('[TiebaDesktop Builder] All processes were GONE. Everything is OK.')


if __name__ == '__main__':
    main()
