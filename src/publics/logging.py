import pathlib
import platform

import aiotieba

import consts


def log_INFO(info: str):
    aiotieba.logging.get_logger().info(info)


def log_WARN(info: str):
    aiotieba.logging.get_logger().warning(info)


def log_exception(error: Exception):
    """在日志中记录一个错误"""
    aiotieba.logging.get_logger().exception(f'[Exception {type(error).__name__}]', exc_info=error)


def init_log():
    """初始化日志系统"""
    if consts.enable_log_file:
        aiotieba.logging.enable_filelog(aiotieba.logging.logging.INFO, pathlib.Path(f'{consts.datapath}/logs'))
    log_INFO(
        f'TiebaDesktop started, App version {consts.APP_VERSION_STR} ({consts.APP_VERSION_NUM}), System {platform.system()} {platform.version()}')
