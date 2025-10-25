"""适用于windows的代理设置模块，该模块会获取系统代理地址并设置在环境变量中"""
import os

if os.name == 'nt':
    import winreg


# 处理代理服务器

class ProxyServer:

    def __init__(self):
        self.__path = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
        self.__INTERNET_SETTINGS = winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER,
                                                    self.__path, 0, winreg.KEY_ALL_ACCESS)

    def get_server_from_Win(self):
        """获取代理配置的ip和端口号"""
        ip, port = "", ""
        if self.is_open_proxy_from_Win():
            try:
                try:
                    ip, port = winreg.QueryValueEx(self.__INTERNET_SETTINGS, "ProxyServer")[0].split(":")
                except:
                    addr = winreg.QueryValueEx(self.__INTERNET_SETTINGS, "ProxyServer")[0].split(";")[0].replace(
                        'http=', '')
                    ip, port = addr.split(':')
            except FileNotFoundError as err:
                print("没有找到代理信息：" + str(err))
            except Exception as err:
                print("有其他报错：" + str(err))
        else:
            print("系统没有开启代理")
        return ip, port

    def is_open_proxy_from_Win(self):
        """判断是否开启了代理"""
        try:
            if winreg.QueryValueEx(self.__INTERNET_SETTINGS, "ProxyEnable")[0] == 1:
                return True
        except FileNotFoundError as err:
            print("没有找到代理信息：" + str(err))
        except Exception as err:
            print("有其他报错：" + str(err))
        return False


def set_proxy():
    if os.name == 'nt':
        proxy_addr = ''
        pxs = ProxyServer()
        if pxs.is_open_proxy_from_Win():
            addr, port = pxs.get_server_from_Win()
            proxy_addr = f'{addr}:{port}'
        if proxy_addr:
            os.environ['HTTP_PROXY'] = f'http://{proxy_addr}'
        else:
            os.environ['HTTP_PROXY'] = ''
    else:
        print('Warning: Your system is not Windows, so can not set proxy')
