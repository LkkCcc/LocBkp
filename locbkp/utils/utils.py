
#  LocBkp - a small backup script
#  Copyright (C) 2022  Locchan <locchan@protonmail.com>
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  (version 2) as published by the Free Software Foundation.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

import json
import os
import tempfile
from stat import *
from locbkp.utils.dictionary import DESTINATION_DIRECTORY, BACKUP_LIST, TYPE_DIRECTORY, TYPE_FILE
import logging
import sys
_format = "%(asctime)s - [%(levelname)-7s] - {}: %(filename)32s:%(lineno)-3s | %(message)s"
default_format = _format.format("LocBkp")

loggers = {}

default_logpath = os.path.join(tempfile.gettempdir(), "LocBkp.log")
default_logger = None

default_level = logging.INFO
progress_bar_resolution_pct = {
    1: 100,
    2: 50,
    20: 20,
    100: 20,
    300: 10,
    500: 5,
    1000: 1
}

wont_backup = []


def get_stream_handlers(logpath, level=logging.INFO, format=default_format):
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(logging.Formatter(format))

    stream_handler_file = logging.FileHandler(logpath, encoding='utf-8')
    stream_handler_file.setLevel(level)
    stream_handler_file.setFormatter(logging.Formatter(format))

    return stream_handler, stream_handler_file


def get_logger(name="LocBkp", level=None, logpath=None):
    global default_logger
    if default_logger is not None:
        return default_logger
    global default_level
    if logpath is None:
        logpath = default_logpath
    if level is None:
        level = default_level
    if name in loggers:
        if loggers[name].level == level:
            return loggers[name]
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers = []
    for ahandler in get_stream_handlers(logpath, level, format=_format.format(name)):
        logger.addHandler(ahandler)
    loggers[name] = logger
    return loggers[name]


def setdebug():
    global default_level
    get_logger().info("Enabling debug logging")
    default_level = logging.DEBUG
    get_logger().debug("Debug logging enabled")


def set_default_logger(alogger):
    global default_logger
    default_logger = alogger


def getdebug():
    return default_level == logging.DEBUG


logger = get_logger()


def closest_divisible(num, divby):
    c1 = num - (num % divby)
    c2 = (num + divby) - (num % divby)
    if num - c1 > c2 - num:
        return c2
    else:
        return c1


def get_progress_bar_resolution(total_items):
    if total_items == 0:
        return 100
    resolutions = progress_bar_resolution_pct.keys()
    resolution = 1
    for anumber in resolutions:
        if total_items > anumber:
            resolution = progress_bar_resolution_pct[resolution]
    return resolution


def progress_bar(current, total):
    if total == 0:
        return
    cur_progress = current / total * 100
    progress_one_percent = total / 100
    resolution = get_progress_bar_resolution(total)
    if current % int(progress_one_percent * resolution) == 0:
        logger.info("{}%".format(closest_divisible(int(cur_progress), resolution)))
    return cur_progress


def get_dir_size_mb(path):
    size = 0
    for path, dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(path, f)
            size += os.path.getsize(fp)
    return size / 1024 / 1024


def stat_file(apath):
    try:
        return os.stat(apath)
    except BaseException as e:
        if apath not in wont_backup:
            logger.warning("Could not stat {}: {}. Will not back up.".format(apath, e.__class__.__name__))
            wont_backup.append(apath)
        return


def get_tree(apath, get_dirs=True):
    result = []
    try:
        st = stat_file(apath)
        if st is None:
            return result
        if get_dirs:
            if S_ISDIR(st.st_mode):
                result = [apath]
                for name in os.listdir(apath):
                    dirs = get_tree(apath+os.sep+name, get_dirs)
                    if dirs is not None:
                        result.extend(dirs)
        else:
            result = [apath]
            if S_ISDIR(st.st_mode):
                for name in os.listdir(apath):
                    dirs = get_tree(apath+os.sep+name, get_dirs)
                    if dirs is not None:
                        result.extend(dirs)
        return result
    except BaseException as e:
        logger.warning("Could not get tree for {}: {}. This file(dir) and everything inside "
                       "(in case it is a dir) will not be backed up".format(apath, e.__class__.__name__))
        return result


def validate_config(config):
    if DESTINATION_DIRECTORY not in config:
        logger.error("Destination directory is not specified in backup list. Cannot proceed, exiting...")
        return False
    if not os.path.exists(config[DESTINATION_DIRECTORY]):
        try:
            os.makedirs(config[DESTINATION_DIRECTORY])
        except BaseException as e:
            logger.error("Destination directory {} does not exist and cannot be created due to {}.\n"
                         "Cannot proceed, exiting...".format(config[DESTINATION_DIRECTORY], e.__class__.__name__))
            return False
    if BACKUP_LIST not in config:
        logger.error("No backup filelist in backup list file. Cannot proceed, exiting...")
        return False
    if len(config[BACKUP_LIST]) == 0:
        logger.warning("Backup filelist is empty. Will not backup anything!")
    newbkplist = []
    for anitem in config[BACKUP_LIST]:
        if not os.path.exists(anitem):
            logger.warning("Path {} does not exist. Will not backup.".format(anitem))
        else:
            newbkplist.append(anitem)
    logger.info("Config is at least semi-valid. Will proceed")
    config[BACKUP_LIST] = newbkplist
    return config


def sanitize_path(*apath):
    apath = list(apath)
    if os.name == 'nt':
        for num, anode in enumerate(apath):
            if num == 0:
                continue
            if ":" in anode:
                apath[num] = anode.replace(":", "")
        respath = os.path.join(*apath)
    else:
        for num, anode in enumerate(apath):
            if num == 0:
                continue
            if anode.startswith("/"):
                apath[num] = str(anode[1:])
        respath = os.path.join(*apath)
    return respath


def get_config(cfg_path):
    backup_list = None
    if os.path.exists(cfg_path):
        with open(cfg_path, "r") as conf_file:
            backup_list = json.load(conf_file)
    else:
        logger.error("Backup list \"{}\" does not exist. Cannot continue.".format(cfg_path))
        return False
    return validate_config(backup_list)

