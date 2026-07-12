"""贴吧账号管理器"""
import asyncio
import os
import shutil
from typing import Optional

import aiotieba
from PyQt5.QtCore import QObject, pyqtSignal

from publics import funcs, app_logger
import consts


def get_user_self_info(bduss, stoken):
    async def get_self_info():
        async with aiotieba.Client(bduss, stoken, proxy=True) as client:
            user_info = await client.get_self_info()

            try:
                error = getattr(user_info, 'err')
            except AttributeError:
                error = None
            if isinstance(error, Exception):
                raise error

            return user_info

    # 获取用户信息
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    user_info = asyncio.run(get_self_info())

    return user_info


class TiebaAccount(QObject):
    """
    贴吧号实例，代表一个已登录的贴吧账号

    Attributes:
        bduss (str): BDUSS，登录令牌
        stoken (str): 贴吧stoken，登录令牌

        portrait (str): 用户 portrait
        nickname (str): 用户新版昵称
        uid (int): 百度用户 ID

        aiotieba_account (aiotieba.Account): aiotieba 的账户信息容器，内含各种贴吧 API 请求参数

        is_current (bool): 是否为当前激活账号
    """

    def __init__(self):
        super().__init__()

        self.bduss = ''
        self.stoken = ''

        self.portrait = ''
        self.nickname = ''
        self.uid = 0

        self.aiotieba_account = aiotieba.Account()

        self.is_current = False

    def init_access_infos(self):
        async def get_access_info():
            """
            获取贴吧风控信息，并装填入 account 对象
            """

            self.aiotieba_account.BDUSS = self.bduss
            self.aiotieba_account.STOKEN = self.stoken

            async with aiotieba.Client(account=self.aiotieba_account, proxy=True) as client:
                aiotieba_http_core = client._http_core

                try:
                    # 并发执行，提高性能
                    result = await asyncio.gather(aiotieba.init_z_id.request(aiotieba_http_core),
                                                  aiotieba.sync.request(aiotieba_http_core),
                                                  aiotieba.login.request(aiotieba_http_core)
                                                  )
                    zid, client_id, sample_id, tbs = result[0], result[1][0], result[1][1], result[2][1]

                    self.aiotieba_account.tbs = tbs
                    self.aiotieba_account.z_id = zid
                    self.aiotieba_account.client_id = client_id
                    self.aiotieba_account.sample_id = sample_id
                except Exception as e:
                    app_logger.log_exception(e)
                    app_logger.log_WARN(f'[account manager] user {self} access info load failed')

        def run_async():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            asyncio.run(get_access_info())
            new_loop.close()

        if not self.aiotieba_account.tbs:
            thread = funcs.start_background_thread(run_async)
            thread.join()

    def init_from_json(self, json_data, current_bduss):
        self.bduss = str(json_data['bduss'])
        self.stoken = str(json_data['stoken'])

        self.portrait = str(json_data['portrait'])
        self.nickname = str(json_data['name'])
        self.uid = int(json_data['uid'])

        self.is_current = current_bduss == self.bduss

    def to_json(self):
        json_data = {'bduss': self.bduss, 'stoken': self.stoken,
                     'portrait': self.portrait,
                     'name': self.nickname,
                     'uid': self.uid}

        return json_data

    def __hash__(self):
        return f'{self.uid}/{self.bduss}'

    def __bool__(self):
        return bool(self.uid)

    def __str__(self):
        return f'AccountObject({self.nickname}/{self.uid}/{self.portrait})'


class AccountManager(QObject):
    accountSwitched = pyqtSignal(TiebaAccount)  # 切换账号时会发出此信号
    accountStateChanged = pyqtSignal()  # 添加、删除、切换、刷新账号时会发出此信号
    addAccountFailed = pyqtSignal(str)  # 添加新账号失败时发出此信号

    def __init__(self):
        super().__init__()

        self.account_list = []
        self.current_account = TiebaAccount()

        self.__is_switching_account = False

    def load_accounts_list_async(self):
        funcs.start_background_thread(self.load_accounts_list)

    def load_accounts_list(self):
        if self.__is_switching_account:
            return

        self.__is_switching_account = True
        last_current_uid = self.current_account.uid

        self.account_list.clear()
        self.current_account = TiebaAccount()

        # 加载用户信息
        current_bduss = ''
        user_data = funcs.load_json_secret(f'{consts.datapath}/user_bduss')

        if not user_data['current_bduss'] and user_data['login_list']:  # 没选账号但是有已登录用户
            # 把当前用户设置成第一个
            current_bduss = user_data['login_list'][0]['bduss']
            user_data['current_bduss'] = current_bduss
            funcs.save_json_secret(user_data, f'{consts.datapath}/user_bduss')
        elif user_data['current_bduss'] and user_data['login_list']:  # 有选账号且有已登录用户
            current_bduss = user_data['current_bduss']

        # 添加所有账号到列表
        for i in user_data['login_list']:
            a = TiebaAccount()
            a.init_from_json(i, current_bduss)

            self.account_list.append(a)
            if a.is_current:
                self.current_account = a
                a.init_access_infos()

        self.__is_switching_account = False
        if last_current_uid != self.current_account.uid or last_current_uid == self.current_account.uid == 0:
            self.accountSwitched.emit(self.current_account)

        self.accountStateChanged.emit()

    def save_accounts_list(self):
        user_data = {'current_bduss': self.current_account.bduss,
                     'login_list': [a.to_json() for a in self.account_list]}

        funcs.save_json_secret(user_data, f'{consts.datapath}/user_bduss')  # 保存配置文件

    def has_any_accounts(self):
        return bool(self.account_list)

    def add_account_async(self, bduss: str, stoken: str, need_process_webview_udf=True):
        funcs.start_background_thread(self.add_account, (bduss, stoken, need_process_webview_udf))

    def add_account(self, bduss: str, stoken: str, need_process_webview_udf=True):
        last_current_uid = self.current_account.uid

        try:
            user_info = get_user_self_info(bduss, stoken)
        except Exception as e:
            app_logger.log_exception(e)
            app_logger.log_WARN('[account manager] get user info failed')
            self.addAccountFailed.emit(funcs.get_exception_string(e))
            return

        # 创建账号实例
        account_object = TiebaAccount()
        account_object.bduss = bduss
        account_object.stoken = stoken
        account_object.uid = user_info.user_id
        account_object.portrait = user_info.portrait
        account_object.nickname = user_info.nick_name if user_info.nick_name else f'百度用户#{user_info.user_id}'

        if not self.has_any_accounts():  # 在没有账号登上去的情况下，把这个账号设置为当前账号
            account_object.is_current = True
            account_object.init_access_infos()
            self.current_account = account_object
        else:
            # 找一下有没有旧的登录信息，有就删除
            for i in self.account_list.copy():
                if i.uid == user_info.user_id:
                    # 如果旧信息是当前账号，把当前账号也更新一次
                    if self.current_account.bduss == i.bduss:
                        account_object.is_current = True
                        account_object.init_access_infos()
                        self.current_account = account_object
                    self.account_list.remove(i)
                    break

        # 添加新的登录信息
        self.account_list.append(account_object)

        # 处理 webview 目录
        if need_process_webview_udf:
            if os.path.isdir(f'{consts.datapath}/webview_data/{user_info.user_id}'):  # 把旧的数据删掉
                shutil.rmtree(f'{consts.datapath}/webview_data/{user_info.user_id}')
            os.mkdir(f'{consts.datapath}/webview_data/{user_info.user_id}')

        # 保存登录信息
        self.save_accounts_list()

        if last_current_uid != self.current_account.uid:
            self.accountSwitched.emit(self.current_account)

        self.accountStateChanged.emit()

        return account_object

    def delete_account_async(self, uid: int):
        funcs.start_background_thread(self.delete_account, (uid,))

    def delete_account(self, uid: int):
        last_current_uid = self.current_account.uid

        for i in self.account_list.copy():
            if i.uid == uid:
                shutil.rmtree(f'{consts.datapath}/webview_data/{i.uid}')
                self.account_list.remove(i)  # 删掉登录信息
                break
        if self.current_account.uid == uid:
            # 如果要删除的账号是当前登录的，换成第一个账号，或设置成空
            if self.has_any_accounts():
                self.current_account = self.account_list[0]
                self.current_account.is_current = True
            else:
                self.current_account = TiebaAccount()

        # 保存登录信息
        self.save_accounts_list()

        if last_current_uid != self.current_account.uid:
            self.accountSwitched.emit(self.current_account)

        self.accountStateChanged.emit()

    def switch_to_account_async(self, uid: int):
        funcs.start_background_thread(self.switch_to_account, (uid,))

    def switch_to_account(self, uid: int):
        if self.__is_switching_account:
            self.addAccountFailed.emit('目前正在切换账号，请等待当前操作完成再切换')
            return

        self.__is_switching_account = True

        # 先取消目前用户的激活状态
        self.current_account.is_current = False

        account = None
        for i in self.account_list:
            if i.uid == uid:
                account = i
                break

        account.is_current = True
        account.init_access_infos()
        self.current_account = account

        # 保存登录信息
        self.save_accounts_list()

        self.__is_switching_account = False
        self.accountSwitched.emit(self.current_account)
        self.accountStateChanged.emit()

    def clear_all_accounts_async(self):
        funcs.start_background_thread(self.clear_all_accounts)

    def clear_all_accounts(self):
        self.account_list.clear()
        self.current_account = TiebaAccount()

        # 保存登录信息
        self.save_accounts_list()

        self.accountSwitched.emit(self.current_account)
        self.accountStateChanged.emit()

    def refresh_all_accounts_info_async(self):
        funcs.start_background_thread(self.refresh_all_accounts_info)

    def refresh_all_accounts_info(self):
        if self.__is_switching_account:
            self.addAccountFailed.emit('目前正在切换账号，请等待当前操作完成再刷新数据')
            return

        self.__is_switching_account = True

        # 留存当前账号信息
        current_uid = self.current_account.uid
        bduss_list = [(i.bduss, i.stoken) for i in self.account_list]

        # 清空已有账号信息
        self.account_list.clear()
        self.current_account = TiebaAccount()

        self.blockSignals(True)
        for bduss, stoken in bduss_list:
            a = self.add_account(bduss, stoken)

            if not a:
                continue

            # 重新设置上新的当前账号
            if a.uid == current_uid:
                a.is_current = True
                a.init_access_infos()
                self.current_account = a
            else:
                a.is_current = False

        if not self.current_account and self.has_any_accounts():
            self.current_account.is_current = True
            self.current_account.init_access_infos()
            self.current_account = self.account_list[0]

        self.save_accounts_list()
        self.blockSignals(False)
        self.__is_switching_account = False

        self.accountStateChanged.emit()

    def get_account_by_uid_portrait(self,
                                    uid: int = 0,
                                    portrait: str = '') -> Optional[TiebaAccount]:
        for a in self.account_list:
            if a.uid == uid or a.portrait == portrait:
                return a


class GlobalAccountContainer:
    account_manager_instance = None

    @classmethod
    def init_manager(cls):
        if cls.account_manager_instance is None:
            cls.account_manager_instance = AccountManager()

    @classmethod
    def get_current_manager(cls) -> AccountManager:
        cls.init_manager()
        return cls.account_manager_instance

    @classmethod
    def get_current_account(cls) -> TiebaAccount:
        return cls.get_current_manager().current_account

    @classmethod
    def get_account_list(cls) -> list[TiebaAccount]:
        return cls.get_current_manager().account_list
