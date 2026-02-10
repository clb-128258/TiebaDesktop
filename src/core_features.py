"""该文件已无实际意义，保留其仅是为了向下兼容"""
from PyQt5.QtCore import QLocale, QTranslator, QTimer, QT_VERSION_STR, QT_VERSION
from PyQt5.QtGui import QPixmapCache
from PyQt5.QtWidgets import QMessageBox, QMenu, QAction, QDialog, QMainWindow, QApplication, QWidgetAction, QCheckBox, \
    QInputDialog

from publics import profile_mgr, webview2, qt_image
from publics import proxytool
from publics.funcs import *
from publics.app_logger import init_log
from publics.app_logger import log_exception, log_INFO, log_WARN
from publics.tb_syncer import *
from publics import top_toast_widget

from subwindow.agree_thread_list import AgreedThreadsList
from subwindow.firstpage_recommend import RecommendWindow
from subwindow.follow_forum_list import FollowForumList
from subwindow.interact_list import UserInteractionsList
from subwindow.tieba_search_entry import TiebaSearchWindow
from subwindow.mainwindow_menu import MainPopupMenu

from ui import mainwindow, settings, login_by_bduss, qr_login

import typing
import sys
import os
import requests
import aiotieba
import aiotieba.helper.cache
import asyncio
import gc
import consts
import shutil
import platform
import time
import copy
import subprocess

if os.name == 'nt':
    import win32api
    import win32con

datapath = consts.datapath
requests.session().trust_env = True
requests.session().verify = False
