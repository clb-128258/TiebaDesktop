"""
主程序构建脚本

Args:
    -m, --makefile: 指定构建配置文件的路径，可不填，如果不填则使用当前目录下的 build_config.json
Notes:
    makefile 是一个 json 文件，用于指定各种配置选项，具体 json 架构可参考 ./build_config.json 文件\n
    在执行构建脚本前，请先删除本目录下的 work_temp 与 work_out 目录（如果有）\n
    构建执行完后，可以在 work_out 目录下找到生成的发行压缩包与安装程序文件。\n
    Windows 下会额外生成 NSIS 安装程序，Linux 下会额外生成 deb 与 rpm 安装包。
"""
import subprocess
import argparse
import datetime
import json
import os
import shutil
import platform


# ---------------------------------------------------------- Linux 打包相关常量

# 包名与可执行文件名，同时也是桌面菜单中使用的图标名
LINUX_PKG_NAME = 'tiebadesktop'
LINUX_EXE_NAME = 'tiebadesktop'

# Linux 下的安装路径（绝对路径，打包时会加上临时根目录前缀）
LINUX_INSTALL_DIR = '/opt/TiebaDesktop'
LINUX_BIN_DIR = '/usr/bin'
LINUX_DESKTOP_DIR = '/usr/share/applications'
LINUX_ICON_DIR = '/usr/share/icons/hicolor/512x512/apps'
LINUX_PIXMAP_DIR = '/usr/share/pixmaps'
LINUX_ICON_THEME_DIR = '/usr/share/icons/hicolor'
LINUX_DOC_DIR = '/usr/share/doc/tiebadesktop'

# Linux 打包过程中使用的临时目录，打包结束后会被删除
LINUX_TEMP_DIR = './work_linux_temp'

# 图标源文件，位于 work_temp 目录下
LINUX_ICON_SRC = 'ui/tieba_logo_big_single.png'

PRODUCT_HOMEPAGE = 'https://github.com/clb-128258/TiebaDesktop'
DEFAULT_LINUX_MAINTAINER = 'CLB <clb-128258@users.noreply.github.com>'
LINUX_SHORT_DESC = '第三方百度贴吧桌面客户端'
LINUX_LONG_DESC = [
    '贴吧桌面（TiebaDesktop）是基于 Python 与 PyQt5 实现的第三方百度贴吧桌面客户端，',
    '包含贴吧浏览、登录与多账号管理、签到、互动消息、用户主页、收藏与浏览历史等功能。',
    '本程序为第三方客户端，与百度官方无关。',
]

# 机器架构名 -> deb 架构名 / rpm 架构名
DEB_ARCH_INDEX = {'AMD64': 'amd64',
                  'x86_64': 'amd64',
                  'i386': 'i386',
                  'i686': 'i386',
                  'x86': 'i386',
                  'aarch64': 'arm64',
                  'arm64': 'arm64',
                  'armv7l': 'armhf'}

RPM_ARCH_INDEX = {'AMD64': 'x86_64',
                  'x86_64': 'x86_64',
                  'i386': 'i386',
                  'i686': 'i386',
                  'x86': 'i386',
                  'aarch64': 'aarch64',
                  'arm64': 'aarch64',
                  'armv7l': 'armv7hl'}

WEEKDAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# 默认运行依赖，可以通过构建配置中的 deb_depends / rpm_requires 字段覆盖
DEFAULT_DEB_DEPENDS = ('libc6, libgcc-s1, libstdc++6, libglib2.0-0, libfontconfig1, libfreetype6, libdbus-1-3, '
                       'libx11-6, libxext6, libxrender1, libxi6, libsm6, libice6, libgl1, libegl1, '
                       'libxkbcommon-x11-0, libxcb1, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, '
                       'libxcb-randr0, libxcb-render-util0, libxcb-cursor0')

DEFAULT_RPM_REQUIRES = ('glibc, libgcc, libstdc++, glib2, fontconfig, freetype, dbus-libs, libX11, libXext, '
                        'libXrender, libXi, libSM, libICE, mesa-libGL, mesa-libEGL, libxkbcommon-x11, libxcb, '
                        'libxcb-util')

# 以下模板中的 [xxx] 均为占位符，打包时会被替换为实际内容
LINUX_LAUNCHER_TPL = """#!/bin/sh
# 由 TiebaDesktop 构建脚本生成的启动脚本，程序本体位于 [install_dir]
exec "[install_dir]/[exe_name]" "$@"
"""

LINUX_DESKTOP_TPL = """[Desktop Entry]
Type=Application
Version=1.0
Name=贴吧桌面
Name[zh_CN]=贴吧桌面
GenericName=第三方百度贴吧客户端
GenericName[zh_CN]=第三方百度贴吧客户端
Comment=[short_desc]
Comment[zh_CN]=[short_desc]
Exec=[exe_name]
Icon=[pkg_name]
Terminal=false
Categories=Network;InstantMessaging;Chat;
Keywords=贴吧;Tieba;BBS;Forum;
StartupNotify=true
StartupWMClass=[exe_name]
"""

LINUX_DEB_CONTROL_TPL = """Package: [pkg_name]
Version: [version]
Section: net
Priority: optional
Architecture: [arch]
Maintainer: [maintainer]
Installed-Size: [installed_size]
Homepage: [homepage]
[depends_line]Description: [short_desc]
[long_desc]
"""

LINUX_DEB_POSTINST_TPL = """#!/bin/sh
set -e

if [ "$1" = "configure" ]; then
    # 刷新桌面数据库与图标缓存，让应用菜单立即显示本程序
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q [desktop_dir] || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f [icon_theme_dir] || true
    fi
fi

exit 0
"""

LINUX_DEB_POSTRM_TPL = """#!/bin/sh
set -e

if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    # 移除后同步刷新桌面数据库与图标缓存
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q [desktop_dir] || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f [icon_theme_dir] || true
    fi
fi

exit 0
"""

LINUX_RPM_SPEC_TPL = """Name:           [pkg_name]
Version:        [version]
Release:        [release]
Summary:        [short_desc]
License:        MIT
URL:            [homepage]
BuildArch:      [arch]
AutoReqProv:    no
[requires_line]
%description
[long_desc]

%prep

%build

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}
cp -a "%{_stage_dir}/." "%{buildroot}/"
rm -rf "%{buildroot}/DEBIAN"

%files
[files]

%post
/usr/bin/update-desktop-database -q 2>/dev/null || :
/usr/bin/gtk-update-icon-cache -q -t -f [icon_theme_dir] 2>/dev/null || :

%postun
/usr/bin/update-desktop-database -q 2>/dev/null || :
/usr/bin/gtk-update-icon-cache -q -t -f [icon_theme_dir] 2>/dev/null || :

%changelog
* [changelog_date] [maintainer] - [version]-[release]
- 由 TiebaDesktop 构建脚本自动生成
"""


def get_system_name():
    system_index = {'Windows': 'win',
                    'Linux': 'linux',
                    'Darwin': 'macos',
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
    arg_parser.add_argument('-m', '--makefile', required=False, default='./build_config.json',
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
    system_name = get_system_name()
    exe_name = f'TiebaDesktop-nsis-installer-{version}-{system_name}.exe'

    with open('./nsis_script.nsi', 'rt', encoding='utf_8_sig') as file:
        nsis_script = file.read()

    nsis_script = nsis_script.replace('[installer_name]', exe_name)
    nsis_script = nsis_script.replace('[verstr]', cfg["version"]['version_string'])

    with open('./_temp_nsis_script.nsi', 'wt', encoding='utf_8_sig') as file:
        file.write(nsis_script)

    args = [cfg['installer_cfg']['makensis_path'],
            './_temp_nsis_script.nsi']
    process = subprocess.Popen(args=args, cwd='.')
    process.wait()
    print(f'[compile_nsis_pkg] makensis process finished with exit code {process.returncode}')
    os.remove('./_temp_nsis_script.nsi')


def stage_path(stage_dir, absolute_path):
    """把绝对路径转换成临时根目录下的路径"""
    return os.path.join(stage_dir, *absolute_path.strip('/').split('/'))


def write_text_file(path, text, mode=None):
    """以 UTF-8 与 LF 换行写入文本文件，可选设置文件权限"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wt', encoding='utf-8', newline='\n') as file:
        file.write(text)
    if mode is not None:
        os.chmod(path, mode)


def get_linux_arch(arch_index):
    """获取 deb / rpm 使用的架构名"""
    machine = platform.machine()
    return arch_index.get(machine, machine.lower())


def get_deb_version(version_string):
    """获取 deb 使用的版本号"""
    version_string = version_string.strip()
    if version_string[:1].lower() == 'v':
        version_string = version_string[1:]
    return version_string


def get_rpm_version(version_string):
    """拆分出 rpm 的 Version 与 Release 字段（rpm 的 Version 字段不允许出现 -）"""
    version_string = version_string.strip()
    if '-' not in version_string:
        return version_string, '1'

    # 在第一个 - 处拆分，保证 Version 字段中不会出现 -；
    # Release 中的 - 会影响 rpm 包名的解析，统一替换为 .
    # 例如 1.3.3-release-github-actions 会得到 Version=1.3.3 与 Release=release.github.actions
    version, release = version_string.split('-', 1)
    return version, release.replace('-', '.')


def get_stage_size_kb(path):
    """统计文件树占用的空间，用于 deb 的 Installed-Size 字段"""
    total_size = 0
    for root, dirs, files in os.walk(path):
        for name in files:
            file_path = os.path.join(root, name)
            if not os.path.islink(file_path):
                total_size += os.path.getsize(file_path)
    return (total_size + 1023) // 1024


def get_changelog_date():
    """获取 rpm changelog 使用的日期，必须为英文的星期与月份"""
    today = datetime.date.today()
    return f'{WEEKDAY_NAMES[today.weekday()]} {MONTH_NAMES[today.month - 1]} {today.day:02d} {today.year}'


def has_dpkg_deb_option(dpkg_deb, option):
    """检测 dpkg-deb 是否支持某个选项，旧版本不支持 --root-owner-group"""
    try:
        output = subprocess.check_output([dpkg_deb, '--help'], stderr=subprocess.STDOUT, text=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return option in output


def run_build_tool(args, failed_msg=None):
    """执行打包工具，失败时抛出异常"""
    print(f'[run_build_tool] {" ".join(args)}')
    process = subprocess.Popen(args=args, cwd='.')
    process.wait()
    if process.returncode != 0:
        raise ChildProcessError(failed_msg or f'{args[0]} process failed with exit code {process.returncode}')
    return process.returncode


def prepare_linux_stage(src_dir, stage_dir):
    """把 work_temp 中的程序文件整理成 deb 与 rpm 共用的安装目录树"""
    app_dir = stage_path(stage_dir, LINUX_INSTALL_DIR)
    shutil.copytree(src_dir, app_dir, symlinks=True)

    exe_path = os.path.join(app_dir, LINUX_EXE_NAME)
    if not os.path.isfile(exe_path):
        raise FileNotFoundError(f'{exe_path} does not exist. '
                                f'Make sure that the executable of the program is named {LINUX_EXE_NAME}.')
    os.chmod(exe_path, 0o755)

    # 从程序自带的资源中取图标，放到系统图标目录下
    icon_src = os.path.join(app_dir, *LINUX_ICON_SRC.split('/'))
    if not os.path.isfile(icon_src):
        raise FileNotFoundError(f'{icon_src} does not exist.')
    for icon_dir in (LINUX_ICON_DIR, LINUX_PIXMAP_DIR):
        icon_dst = os.path.join(stage_path(stage_dir, icon_dir), f'{LINUX_PKG_NAME}.png')
        os.makedirs(os.path.dirname(icon_dst), exist_ok=True)
        shutil.copy2(icon_src, icon_dst)

    # 版权文件
    doc_dir = stage_path(stage_dir, LINUX_DOC_DIR)
    os.makedirs(doc_dir, exist_ok=True)
    shutil.copy2('./mit_license.txt', os.path.join(doc_dir, 'copyright'))

    # 启动脚本，保证程序的工作目录始终是程序本体所在的目录
    launcher = LINUX_LAUNCHER_TPL.replace('[install_dir]', LINUX_INSTALL_DIR)
    launcher = launcher.replace('[exe_name]', LINUX_EXE_NAME)
    write_text_file(os.path.join(stage_path(stage_dir, LINUX_BIN_DIR), LINUX_PKG_NAME), launcher, 0o755)

    # 桌面菜单入口
    desktop_entry = LINUX_DESKTOP_TPL.replace('[short_desc]', LINUX_SHORT_DESC)
    desktop_entry = desktop_entry.replace('[pkg_name]', LINUX_PKG_NAME)
    desktop_entry = desktop_entry.replace('[exe_name]', LINUX_PKG_NAME)
    desktop_file = os.path.join(stage_path(stage_dir, LINUX_DESKTOP_DIR), f'{LINUX_PKG_NAME}.desktop')
    write_text_file(desktop_file, desktop_entry)

    print(f'[prepare_linux_stage] package files are ready at {stage_dir}')


def compile_deb_pkg(cfg, stage_dir):
    """生成 deb 安装包，需要 dpkg-deb 工具"""
    print('[compile_deb_pkg] compiling deb package')

    dpkg_deb = shutil.which('dpkg-deb')
    if dpkg_deb is None:
        print('[compile_deb_pkg] dpkg-deb was not found, the deb package is skipped. '
              'Install it (for example "sudo apt install dpkg") and try again')
        return

    installer_cfg = cfg.get('installer_cfg', {})
    version = get_deb_version(cfg['version']['version_string'])
    arch = get_linux_arch(DEB_ARCH_INDEX)
    depends = installer_cfg.get('deb_depends', DEFAULT_DEB_DEPENDS)

    control = LINUX_DEB_CONTROL_TPL.replace('[pkg_name]', LINUX_PKG_NAME)
    control = control.replace('[version]', version)
    control = control.replace('[arch]', arch)
    control = control.replace('[maintainer]', installer_cfg.get('linux_maintainer', DEFAULT_LINUX_MAINTAINER))
    control = control.replace('[homepage]', PRODUCT_HOMEPAGE)
    control = control.replace('[installed_size]', str(get_stage_size_kb(stage_dir)))
    control = control.replace('[depends_line]', f'Depends: {depends}\n' if depends else '')
    control = control.replace('[short_desc]', LINUX_SHORT_DESC)
    control = control.replace('[long_desc]', '\n'.join(' ' + i for i in LINUX_LONG_DESC))

    postinst = LINUX_DEB_POSTINST_TPL.replace('[desktop_dir]', LINUX_DESKTOP_DIR)
    postinst = postinst.replace('[icon_theme_dir]', LINUX_ICON_THEME_DIR)
    postrm = LINUX_DEB_POSTRM_TPL.replace('[desktop_dir]', LINUX_DESKTOP_DIR)
    postrm = postrm.replace('[icon_theme_dir]', LINUX_ICON_THEME_DIR)

    ctrl_dir = os.path.join(stage_dir, 'DEBIAN')
    write_text_file(os.path.join(ctrl_dir, 'control'), control)
    write_text_file(os.path.join(ctrl_dir, 'postinst'), postinst, 0o755)
    write_text_file(os.path.join(ctrl_dir, 'postrm'), postrm, 0o755)

    deb_name = f'TiebaDesktop-{cfg["version"]["version_string"]}-{get_system_name()}.deb'
    deb_path = os.path.abspath(os.path.join('./work_out', deb_name))

    if has_dpkg_deb_option(dpkg_deb, '--root-owner-group'):
        args = [dpkg_deb, '--build', '--root-owner-group', os.path.abspath(stage_dir), deb_path]
    elif shutil.which('fakeroot') is not None:
        # 老版本的 dpkg-deb 不支持 --root-owner-group，用 fakeroot 代替
        args = ['fakeroot', dpkg_deb, '--build', os.path.abspath(stage_dir), deb_path]
    else:
        args = [dpkg_deb, '--build', os.path.abspath(stage_dir), deb_path]

    run_build_tool(args, failed_msg='dpkg-deb process failed!')
    print(f'[compile_deb_pkg] {deb_name} has been generated')


def compile_rpm_pkg(cfg, stage_dir, top_dir):
    """生成 rpm 安装包，需要 rpmbuild 工具"""
    print('[compile_rpm_pkg] compiling rpm package')

    if shutil.which('rpmbuild') is None:
        print('[compile_rpm_pkg] rpmbuild was not found, the rpm package is skipped. '
              'Install it (for example "sudo apt install rpm" or "sudo dnf install rpm-build") and try again')
        return

    installer_cfg = cfg.get('installer_cfg', {})
    rpm_version, rpm_release = get_rpm_version(cfg['version']['version_string'])
    arch = get_linux_arch(RPM_ARCH_INDEX)
    requires = installer_cfg.get('rpm_requires', DEFAULT_RPM_REQUIRES)

    files = [LINUX_INSTALL_DIR,
             f'{LINUX_BIN_DIR}/{LINUX_PKG_NAME}',
             f'{LINUX_DESKTOP_DIR}/{LINUX_PKG_NAME}.desktop',
             f'{LINUX_ICON_DIR}/{LINUX_PKG_NAME}.png',
             f'{LINUX_PIXMAP_DIR}/{LINUX_PKG_NAME}.png',
             f'{LINUX_DOC_DIR}/copyright']

    spec = LINUX_RPM_SPEC_TPL.replace('[pkg_name]', LINUX_PKG_NAME)
    spec = spec.replace('[version]', rpm_version)
    spec = spec.replace('[release]', rpm_release)
    spec = spec.replace('[arch]', arch)
    spec = spec.replace('[short_desc]', LINUX_SHORT_DESC)
    spec = spec.replace('[long_desc]', '\n'.join(LINUX_LONG_DESC))
    spec = spec.replace('[homepage]', PRODUCT_HOMEPAGE)
    spec = spec.replace('[requires_line]', f'Requires:       {requires}\n' if requires else '')
    spec = spec.replace('[files]', '\n'.join(files))
    spec = spec.replace('[icon_theme_dir]', LINUX_ICON_THEME_DIR)
    spec = spec.replace('[changelog_date]', get_changelog_date())
    spec = spec.replace('[maintainer]', installer_cfg.get('linux_maintainer', DEFAULT_LINUX_MAINTAINER))

    for sub_dir in ('BUILD', 'BUILDROOT', 'RPMS', 'SOURCES', 'SPECS', 'SRPMS'):
        os.makedirs(os.path.join(top_dir, sub_dir), exist_ok=True)
    spec_path = os.path.join(top_dir, 'SPECS', f'{LINUX_PKG_NAME}.spec')
    write_text_file(spec_path, spec)

    run_build_tool(['rpmbuild',
                    '-bb',
                    '--define', f'_topdir {top_dir}',
                    '--define', f'_stage_dir {os.path.abspath(stage_dir)}',
                    # 关闭 debuginfo 子包，避免依赖 debuginfo 相关工具
                    '--define', 'debug_package %{nil}',
                    spec_path],
                   failed_msg='rpmbuild process failed!')

    built_rpm = os.path.join(top_dir, 'RPMS', arch, f'{LINUX_PKG_NAME}-{rpm_version}-{rpm_release}.{arch}.rpm')
    if not os.path.isfile(built_rpm):
        raise FileNotFoundError(f'{built_rpm} does not exist. rpmbuild failed to generate the package.')

    rpm_name = f'TiebaDesktop-{cfg["version"]["version_string"]}-{get_system_name()}.rpm'
    shutil.copy2(built_rpm, os.path.join('./work_out', rpm_name))
    print(f'[compile_rpm_pkg] {rpm_name} has been generated')


def compile_linux_pkg(cfg):
    """在 Linux 下生成 deb 与 rpm 安装包"""
    if platform.system() != 'Linux':
        return

    installer_cfg = cfg.get('installer_cfg', {})
    build_deb = installer_cfg.get('build_deb', True)
    build_rpm = installer_cfg.get('build_rpm', True)
    if not (build_deb or build_rpm):
        return

    print('[compile_linux_pkg] preparing linux package files')
    os.makedirs('./work_out', exist_ok=True)

    linux_temp_dir = os.path.abspath(LINUX_TEMP_DIR)
    if os.path.isdir(linux_temp_dir):
        shutil.rmtree(linux_temp_dir)

    stage_dir = os.path.join(linux_temp_dir, 'files')
    top_dir = os.path.join(linux_temp_dir, 'rpmbuild')
    try:
        prepare_linux_stage('./work_temp', stage_dir)
        if build_rpm:
            compile_rpm_pkg(cfg, stage_dir, top_dir)
        if build_deb:
            compile_deb_pkg(cfg, stage_dir)
    finally:
        print(f'[compile_linux_pkg] removing {LINUX_TEMP_DIR}')
        shutil.rmtree(linux_temp_dir, ignore_errors=True)


def pack_compressed(cfg):
    print('[pack_compressed] compressing zip package')

    if not os.path.isdir('./work_out'):
        os.mkdir('./work_out')

    version = cfg['version']['version_string']
    system_name = get_system_name()
    zip_name = f'TiebaDesktop-{version}-{system_name}.zip'
    args = [cfg['sevenzip_path'],
            'a',
            '-tzip',
            '-mx=5',
            './work_out/' + zip_name,
            './work_temp/*', ]
    process = subprocess.Popen(args=args, cwd='.')
    process.wait()
    print(f'[pack_compressed] 7-zip process finished with exit code {process.returncode}')


def cleanup_binres_for_linux(binres_dir='./work_temp/binres'):
    """
    Linux 打包时清理 binres 目录。

    binres 中的 .exe 与 .dll 都是 Windows 专属的依赖文件（WebView2、toast、ShareBridge、ffmpeg.exe 等），
    在 Linux 下不会被使用，只会白白占用发行包的空间，因此这里只保留没有后缀名的 linux 二进制文件
    （例如音频播放器使用的 binres/ffmpeg），其余文件一律删除。
    """
    if not os.path.isdir(binres_dir):
        return

    deleted_count = 0
    deleted_size = 0

    # topdown=False 保证先处理子目录中的文件，再判断父目录是否已被清空
    for root, dirs, files in os.walk(binres_dir, topdown=False):
        for name in files:
            if not os.path.splitext(name)[1]:
                # 没有后缀名的文件是 linux 二进制文件，需要保留
                continue

            file_path = os.path.join(root, name)
            deleted_size += os.path.getsize(file_path)
            os.remove(file_path)
            deleted_count += 1
            print(f'[cleanup_binres_for_linux] {file_path} has been deleted')

        if root != binres_dir and not os.listdir(root):
            os.rmdir(root)
            print(f'[cleanup_binres_for_linux] empty dir {root} has been deleted')

    print(f'[cleanup_binres_for_linux] {deleted_count} useless files are deleted, '
          f'{deleted_size / 1024 / 1024:.2f} MB of disk space is saved')


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
    if os.name != 'nt':
        # linux 下只保留 binres 中没有后缀名的二进制文件
        cleanup_binres_for_linux()
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

    if os.name == 'nt':
        args = [cfg['py_environ_path'] + r'\Scripts\pyinstaller.exe',
                '-D',
                '-w',
                '--version-file',
                r'.\..\_temp_windows_version_info.txt',
                '-i',
                r'.\ui\tieba_logo_big_single.ico',
                r'.\main.py']
    else:
        args = [cfg['py_environ_path'] + '/bin/pyinstaller',
                '-D',
                '-w',
                r'./main.py']

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
    compile_linux_pkg(mkfile_config)

    print('[TiebaDesktop Builder] All processes were GONE. Everything is OK.')


if __name__ == '__main__':
    main()
