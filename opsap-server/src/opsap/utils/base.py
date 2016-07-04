# coding: utf-8
# Author: Dunkle Qiu

import logging
import subprocess
from opsap.settings import *
from django.http import QueryDict
from rest_framework.parsers import DataAndFiles


def set_log(level, filename='opsap.log'):
    """
    根据提示设置log打印
    """
    if not os.path.isdir(LOG_DIR):
        os.makedirs(LOG_DIR)
    log_file = os.path.join(LOG_DIR, filename)
    if not os.path.isfile(log_file):
        os.mknod(log_file)
        os.chmod(log_file, 0644)
    log_level_total = {'debug': logging.DEBUG, 'info': logging.INFO, 'warning': logging.WARN, 'error': logging.ERROR,
                       'critical': logging.CRITICAL}
    logger_f = logging.getLogger('opsap')
    logger_f.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_file)
    fh.setLevel(log_level_total.get(level, logging.DEBUG))
    formatter = logging.Formatter('%(asctime)s [%(filename)s:%(lineno)d] %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger_f.addHandler(fh)
    return logger_f


logger = set_log(LOG_LEVEL)


def bash(cmd):
    """
    执行bash命令
    """
    return subprocess.call(cmd, shell=True)


# 请求处理
def post_data_to_dict(data):
    """
    将request.data类型统一为dict
    """
    if isinstance(data, QueryDict):
        return data.dict()
    elif isinstance(data, DataAndFiles):
        return data.data.dict()
    else:
        return data
