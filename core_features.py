"""核心模块，实现了程序内大部分功能，本程序的主要函数和类均封装在此处"""
from PyQt5.QtCore import QLocale, QTranslator, QTimer, QT_VERSION_STR, QT_VERSION
from PyQt5.QtGui import QPixmapCache
from PyQt5.QtWidgets import QMessageBox, QMenu, QAction, QDialog, QMainWindow, QApplication, QWidgetAction

from publics import profile_mgr, webview2
from publics import proxytool
from publics.funcs import *
from publics.logging import init_log
from publics.logging import log_exception, log_INFO
from publics.tb_syncer import *
from publics import top_toast_widget

from subwindow.agree_thread_list import AgreedThreadsList
from subwindow.firstpage_recommend import RecommandWindow
from subwindow.follow_forum_list import FollowForumList
from subwindow.interact_list import UserInteractionsList
from subwindow.star_thread_list import StaredThreadsList
from subwindow.tieba_search_entry import TiebaSearchWindow
from subwindow.user_home_page import UserHomeWindow
from subwindow.history_list import HistoryViewWindow
from subwindow.mainwindow_menu import MainPopupMenu

from ui import mainwindow, settings, login_by_bduss

import sys
import os
import requests
import aiotieba
import aiotieba.helper.cache
import asyncio
import gc
import consts
import shutil
import locale
import platform
import time

if os.name == 'nt':
    import win32api
    import win32con

datapath = consts.datapath
requests.session().trust_env = True
requests.session().verify = False
