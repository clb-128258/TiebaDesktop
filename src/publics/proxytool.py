"""代理设置模块"""
import os
from publics import profile_mgr, app_logger


class WindowsProxyServer:
    def __init__(self):
        import winreg
        self.__path = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
        self.__INTERNET_SETTINGS = winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER,
                                                    self.__path, 0, winreg.KEY_ALL_ACCESS)

    def get_server_from_Win(self):
        import winreg

        ip, port = "", ""
        if self.is_open_proxy_from_Win():
            try:
                try:
                    ip, port = winreg.QueryValueEx(self.__INTERNET_SETTINGS, "ProxyServer")[0].split(":")
                except:
                    addr = winreg.QueryValueEx(self.__INTERNET_SETTINGS, "ProxyServer")[0].split(";")[0].replace(
                        'http=', '')
                    ip, port = addr.split(':')
            except Exception as err:
                logging.log_exception(err)
        return ip, port

    def is_open_proxy_from_Win(self):
        try:
            import winreg
            if winreg.QueryValueEx(self.__INTERNET_SETTINGS, "ProxyEnable")[0] == 1:
                return True
        except Exception as e:
            app_logger.log_exception(e)
        return False


def set_proxy():
    try:
        ip, port = '', ''
        os.environ['HTTP_PROXY'] = ''
        os.environ['HTTPS_PROXY'] = ''
        os.environ['no_proxy'] = ''

        if profile_mgr.local_config['proxy_settings']['proxy_switch'] == 1:
            if os.name == 'nt':
                proxy = WindowsProxyServer()
                ip, port = proxy.get_server_from_Win()
        elif profile_mgr.local_config['proxy_settings']['proxy_switch'] == 2:
            ip, port = profile_mgr.local_config['proxy_settings']['custom_proxy_server']['ip'], str(
                profile_mgr.local_config['proxy_settings']['custom_proxy_server']['port'])

        if ip and port:
            if profile_mgr.local_config['proxy_settings']['enabled_scheme']['http']:
                os.environ['HTTP_PROXY'] = f'http://{ip}:{port}'
            if profile_mgr.local_config['proxy_settings']['enabled_scheme']['https']:
                os.environ['HTTPS_PROXY'] = f'https://{ip}:{port}'
        else:
            os.environ['no_proxy'] = '*'
    except Exception as e:
        logging.log_WARN('Warning: proxy settings was not set')
        app_logger.log_exception(e)
