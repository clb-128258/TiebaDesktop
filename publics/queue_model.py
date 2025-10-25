"""任务处理队列模型"""
import queue
import threading
import time


class QueueProcess:
    """
    队列中的任务

    Args:
        args: 任务参数
    Notes:
        result_queue: 用于获取执行结果的队列
    """

    def __init__(self, args: tuple):
        self.process_args = args
        self.result_queue = queue.Queue(3)


class QueueModel:
    """缓存处理队列模型，支持在高并发场景下使数据的存取有序，防止程序出现线程锁卡死"""

    def __init__(self):
        self.request_queue = queue.Queue()

        self.request_queue_thread = threading.Thread(target=self.main_handler, daemon=True)
        self.request_queue_thread.start()

    def create_process_await(self, args: tuple):
        """发起新任务，并返回结果"""
        new_process = QueueProcess(args)
        self.request_queue.put(new_process)

        while new_process.result_queue.empty():
            time.sleep(0.1)
        return new_process.result_queue.get()

    def handle_process(self, process: QueueProcess):
        """处理任务，此处应当重写，并使该函数返回任意执行结果"""
        return 0

    def main_handler(self):
        """主处理线程"""
        while 1:
            while not self.request_queue.empty():
                process = self.request_queue.get()
                result_data = self.handle_process(process)
                process.result_queue.put(result_data)
            time.sleep(1)
