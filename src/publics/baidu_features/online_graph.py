"""百度识图相关功能封装"""

from publics import app_logger
from publics import funcs, request_mgr

import time
import requests
from PyQt5.QtCore import QObject, pyqtSignal

api_header = {
    'User-Agent': request_mgr.header_android['User-Agent'],
    'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    'Accept-Encoding': "gzip, deflate",
    'Upgrade-Insecure-Requests': "1",
    'X-Requested-With': "com.baidu.tieba",
    'Accept-Language': "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
}


class BaiduGraphSensor(QObject):
    # 定义信号：图片链接获取完成，传递识图结果页面URL
    imageResultUrlGot = pyqtSignal(str)

    def __init__(self):
        super().__init__()

    def get_image_result_url(self, image_url: str) -> str:
        """
        获取特定图片url的识图结果页面

        Args:
            image_url: 图片链接

        Returns:
            识图结果页面的URL
        """
        try:
            # 构建请求 Base URL
            url = f"https://graph.baidu.com/details"

            # 请求 URL 参数
            params = {
                "image": image_url,
                "carousel": "0",
                "tn": "tieba",
                "promotion_name": "shitu",
                "cuid_gid": "",
                "timestamp": str(int(time.time() * 1000)),
                "_client_version": request_mgr.TIEBA_CLIENT_VERSION,
                "_client_type": "2",
                "nohead": "0"
            }

            response = requests.get(url,
                                    params=params,
                                    headers=api_header,
                                    timeout=13,
                                    verify=request_mgr.is_ssl_required(),
                                    allow_redirects=True)

            final_url = response.url
            if final_url:
                final_url = final_url + '&tpl_from=pc&isLogoShow=1'
                app_logger.log_INFO(f'[baidu image sensor] get image result webpage succeed: {final_url}')
                return final_url
            else:
                raise ValueError('api returned a empty url')

        except Exception as e:
            app_logger.log_exception(e)
            return ""

    def _fetch_image_url_worker(self, image_url: str):
        """
        后台线程工作函数，获取链接并发射信号

        Args:
            image_url: 图片链接
        """
        result_url = self.get_image_result_url(image_url)
        if result_url:
            self.imageResultUrlGot.emit(result_url)

    def get_image_result_url_async(self, image_url: str):
        """
        异步获取百度识图结果链接

        Args:
            image_url: 图片链接
        """
        funcs.start_background_thread(self._fetch_image_url_worker, args=(image_url,))
