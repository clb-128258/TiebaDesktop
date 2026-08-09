import asyncio
import os
import shutil
import subprocess
import sys

import aiotieba
import aiotieba.helper.cache

import consts
from publics import account_mgr, toasting
from publics.app_logger import log_INFO
from publics.baidu_features import tieba_apis

if os.name == 'nt':
    import win32api
    import win32con


class CliFunctions:
    def __init__(self, cmd_argv):
        self.cmds = cmd_argv

    def get_current_user(self):
        account_mgr_obj = account_mgr.GlobalAccountContainer.get_current_manager()
        account_mgr_obj.load_accounts_list()
        return account_mgr_obj.current_account.bduss, account_mgr_obj.current_account.stoken

    def msgbox(self, text, title='贴吧桌面'):
        if '--quiet' not in self.cmds and os.name == 'nt':
            win32api.MessageBox(None, text, title, win32con.MB_OK | win32con.MB_ICONINFORMATION)

    def msgbox_ask(self, text, title='贴吧桌面'):
        if '--quiet' not in self.cmds and os.name == 'nt':
            return win32api.MessageBox(None, text, title, win32con.MB_YESNO) == win32con.IDYES
        else:
            return os.name == 'nt'

    async def sign_grow(self):
        log_INFO('--sign-grows started')

        bduss, stoken = self.get_current_user()
        if not bduss:
            self.msgbox('请先登录账号再签到。')
            return
        async with aiotieba.Client(bduss, stoken, proxy=True) as client:
            r1 = await client.sign_growth()
            r2 = await client.sign_growth_share()

            err_msg = '成长等级签到成功。'
            if not (r1 and r2):
                err_msg = '签到失败，详情如下：'
                if not r1:
                    err_msg += f'\n成长等级签到：{r1.err}'
                if not r2:
                    err_msg += f'\n成长等级分享任务：{r2.err}'
            self.msgbox(err_msg)

    async def sign_all(self):
        log_INFO('--sign-all-forums started')

        bduss, stoken = self.get_current_user()
        signed_count = 0

        if not bduss:
            self.msgbox('请先登录账号再签到。')
            return

        async with aiotieba.Client(bduss, stoken, proxy=True) as client:
            await client.sign_forums()  # 先一键签到

            bars = tieba_apis.newmoindex(bduss)['data']['like_forum']
            bars.sort(key=lambda k: int(k["user_exp"]), reverse=True)  # 按吧等级排序

            for forum in bars:
                if forum["is_sign"] != 1:
                    fid = forum['forum_id']
                    fname = forum['forum_name']
                    r = tieba_apis.sign_forum(bduss, stoken, fid, fname)['error_code'] == '0'

                    signed_count += (1 if r else 0)
                    await asyncio.sleep(0.3)  # 休眠0.3秒，防止贴吧服务器抽风
                else:
                    # 已签到的直接跳过
                    signed_count += 1
        self.msgbox(f'签到完成，已签到 {signed_count} 个吧，{len(bars) - signed_count} 个吧签到失败。')

    async def switch_account(self):
        log_INFO('--set-current-account started')

        uid = -1
        for i in self.cmds:
            if i.startswith('--userid='):
                try:
                    uid = int(i.split('=')[1])
                except:
                    uid = -1

        if uid <= 0:
            self.msgbox('请指定正确的用户 ID。')
        else:
            account_mgr_obj = account_mgr.GlobalAccountContainer.get_current_manager()
            account_mgr_obj.load_accounts_list()

            for i in account_mgr_obj.account_list:
                if i.uid == uid:
                    account_mgr_obj.switch_to_account(uid)
                    self.msgbox(f'已将账号切换到 {uid}。')
                    return
            self.msgbox(f'未在本地找到 {uid} 的登录信息。')

    def start_async(self, func):
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        asyncio.run(func)

    def uninstall_cleanup(self):
        aiotieba.logging.set_logger(aiotieba.logging.TiebaLogger())

        # 结束正在运行的进程
        killname = 'tiebadesktop.exe'
        current_pid = os.getpid()
        if os.name == 'nt':
            preq = os.popen('tasklist /fi "imagename eq {}"'.format(killname))
            pidlist = []

            for p in preq:
                plist = p.split(" ")
                for pl in plist:
                    if pl.isnumeric() and pl is not killname and int(pl) != current_pid:
                        pidlist.append(pl)
                        break
            for pid in pidlist:
                subprocess.call(f'taskkill /f /pid {pid}', shell=True)

        elif os.name == 'posix':
            # Get the list of processes matching the name
            try:
                result = subprocess.check_output(['pgrep', '-f', killname], text=True)
                pidlist = [int(pid) for pid in result.split() if int(pid) != current_pid]

                # Kill each process
                for pid in pidlist:
                    subprocess.call(['kill', '-9', str(pid)])
            except subprocess.CalledProcessError:
                # pgrep returns non-zero if no process is found
                pass

        # 删除 AUMID
        toasting.delete_AUMID(consts.WINDOWS_AUMID)

        # 清空用户数据
        need_del = self.msgbox_ask('你是否希望删除用户数据？\n'
                                   '这些用户数据包括登录信息、偏好选项、历史记录等，删除后不可恢复。')
        if need_del:
            shutil.rmtree(consts.datapath)


def handle_command_events():
    """处理命令行参数，与命令行参数有关的代码均在此执行"""
    cmds = sys.argv
    dont_run_gui = False
    cli = CliFunctions(cmds)

    log_INFO('Handling command args')

    if '--set-current-account' in cmds:
        dont_run_gui = True
        cli.start_async(cli.switch_account())
    elif '--uninstall-cleanup' in cmds:
        dont_run_gui = True
        cli.uninstall_cleanup()
    else:
        if '--sign-all-forums' in cmds:
            dont_run_gui = True
            cli.start_async(cli.sign_all())

        if '--sign-grows' in cmds:
            dont_run_gui = True
            cli.start_async(cli.sign_grow())
    if dont_run_gui:
        sys.exit(0)


def reset_udf():
    """根据命令行参数重设datapath"""
    cmds = sys.argv
    if '--reset-udf' in cmds:
        udf = ''
        for i in cmds:
            if i.startswith('--udf-path='):
                udf = i.split('=')[1]

        if not os.path.isdir(udf):
            log_INFO(f'{udf} is not a valid folder. creating..')
            os.mkdir(udf)

        if os.path.isdir(udf):
            consts.datapath = udf
            log_INFO(f'UserDataPath is reset by --reset-udf.')

        log_INFO(f'Now UserDataPath is {consts.datapath}.')
