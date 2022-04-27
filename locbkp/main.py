import json
from datetime import datetime, timedelta

time_start = datetime.now()
time_preparation = timedelta(seconds=0)
time_preparation_finished = time_start
time_copy_temp = timedelta(seconds=0)
time_copy_temp_finished = time_start
time_compress = timedelta(seconds=0)
time_compress_finished = time_start
time_transfer = timedelta(seconds=0)
time_transfer_finished = time_start
time_cleanup = timedelta(seconds=0)
time_cleanup_finished = time_start
files_backed = []
dirs_backed = []
size_before_compression = 0.0
size_after_compression = 0.0

import os.path
import shutil
import subprocess
import tempfile
import argparse
from locbkp.utils.dictionary import BACKUP_LIST, DESTINATION_DIRECTORY
from locbkp.utils.logger import get_logger
from locbkp.utils.utils import get_config, get_tree, sanitize_path, get_dir_size_mb, progress_bar

if os.name == "nt":
    p7z_path = "C:\\Program Files\\7-Zip\\7z.exe"
else:
    p7z_path = "7z"

version = "0.0.1"
logger = get_logger()

curdate = time_start.strftime("%d-%m-%Y_%H.%M.%S")
temp = tempfile.gettempdir()
packing_directory = os.path.join(temp, curdate)
archive_name = "backup_{}.7z".format(curdate)
archive_path = os.path.join(temp, archive_name)


def prepare_backup_lists(backup_list):
    files_to_bkp = []
    dirs_to_bkp = []
    for anitem in backup_list:
        newfiles = get_tree(anitem, False)
        newdirs = get_tree(anitem, True)
        for afile in newfiles:
            if afile not in files_to_bkp:
                files_to_bkp.append(afile)
                dirpath = os.path.split(afile)[:-1]
                if not sanitize_path(*dirpath) in dirs_to_bkp:
                    dirs_to_bkp.append(sanitize_path(*dirpath))
        for adir in newdirs:
            if adir not in dirs_to_bkp:
                dirs_to_bkp.append(adir)
    return files_to_bkp, dirs_to_bkp


def start_backup(backup_list_path):
    global time_preparation, time_preparation_finished
    try:
        os.makedirs(packing_directory)
    except BaseException as e:
        logger.error("Could not create temp directory: {}. Cannot proceed, exiting...".format(e.__class__.__name__))
        exit(1)
    backup_list = get_config(backup_list_path)
    files, dirs = prepare_backup_lists(backup_list[BACKUP_LIST])
    time_preparation_finished = datetime.now()
    time_preparation = time_preparation_finished - time_start
    backup(backup_list[DESTINATION_DIRECTORY], files, dirs)


def backup(destdir, files, dirs):
    global time_copy_temp, time_copy_temp_finished
    logger.info("Creating directory structure...")
    logger.info("Will create {} directories...".format(len(dirs)))
    backup_empty_dirs(dirs)

    logger.info("Backing up {} files to {}...".format(len(files), packing_directory))
    backup_files(files)
    logger.info("Done backing up files.")
    time_copy_temp_finished = datetime.now()
    time_copy_temp = time_copy_temp_finished - time_preparation_finished
    backup_finalize(destdir)


def generate_backup_report(backup_size):
    try:
        with open(os.path.join(packing_directory, "LocBkp_report_{}.json".format(curdate)), "w") as locbkp_report:
            json.dump(
                {
                    "files_backed": files_backed,
                    "dirs_backed": dirs_backed,
                    "size_uncompressed_mb": backup_size
                },
                locbkp_report
            )
    except BaseException as e:
        logger.error("Could not create backup report! Error: {}".format(e.__class__.__name__))


def backup_empty_dirs(dirlist):
    for adir in dirlist:
        final_path = sanitize_path(packing_directory, adir)
        try:
            # logger.info("Backing up directory structure: {} to {}".format(adir, final_path))
            os.makedirs(final_path)
            dirs_backed.append(adir)
        except FileExistsError:
            pass
        except BaseException as e:
            logger.warning("Could not create a directory {}: {}".format(final_path, e.__class__.__name__))


def backup_files(fileslist):
    global files_backed
    total_files = len(fileslist)
    for num, afile in enumerate(fileslist):
        progress_bar(num, total_files)
        if os.path.exists(afile) and os.path.isfile(afile):
            if backup_file(afile):
                files_backed.append(sanitize_path(afile, packing_directory))


def backup_finalize(destdir):
    global time_compress, time_transfer, size_before_compression, size_after_compression,\
        time_compress_finished, time_transfer_finished, time_cleanup_finished, time_cleanup
    logger.info("Backup finished. Finalizing...")
    size_before_compression = get_dir_size_mb(packing_directory)
    logger.info("Backed up {:.3f}Mb of data.".format(size_before_compression))
    logger.info("Generating backup report...")
    generate_backup_report(size_before_compression)
    logger.info("Compressing backup...")
    p7z_cmd = [p7z_path, "a", "-t7z", archive_path, "-mx9", "-aoa", packing_directory]
    # logger.info("Executing: {}".format(" ".join(p7z_cmd)))
    time_pre_compress = datetime.now()
    process = subprocess.Popen(p7z_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    process.wait()
    time_compress_finished = datetime.now()
    time_compress = time_compress_finished - time_pre_compress
    size_after_compression = os.path.getsize(archive_path) / 1024 / 1024
    logger.info("Backup is compressed. Compressed size is {:.3f}Mb".format(size_after_compression))
    logger.info("Transferring backup to destination location...")
    time_pre_transfer = datetime.now()
    shutil.copy(archive_path, os.path.join(destdir, archive_name))
    time_transfer_finished = datetime.now()
    time_transfer = time_transfer_finished - time_pre_transfer
    logger.info("Done. Cleaning up...")
    os.remove(archive_path)
    shutil.rmtree(packing_directory)
    logger.info("Cleaned up.")
    time_cleanup_finished = datetime.now()
    time_cleanup = time_cleanup_finished - time_transfer_finished


def backup_file(file_path):
    destination = sanitize_path(packing_directory, file_path)
    # logger.info("Backing up {} to {}".format(file_path, destination))
    shutil.copy(file_path, destination)
    return True


parser = argparse.ArgumentParser()
parser.add_argument("backup_list_path", help="Backup list to use.", type=str)
args = parser.parse_args()

logger.info("LocBkp v.{} started.".format(version))

start_backup(args.backup_list_path)


total_time = datetime.now() - time_start
logger.info("Backed up {} files and {} directories.".format(len(files_backed), len(dirs_backed)))
logger.info("Time: Preparation: {:.3f}s; Copy: {:.3f}s; Compress: {:.3f}s; Transfer: {:.3f}s; Cleanup: {:3f}s."
            .format(time_preparation.total_seconds(), time_copy_temp.total_seconds(), time_compress.total_seconds(),
                    time_transfer.total_seconds(), time_cleanup.total_seconds()))
logger.info("Compression effectiveness is {:.2f}%".format(100 - (size_after_compression / size_before_compression) * 100))
logger.info("Total time is {:.3f}s.".format(total_time.total_seconds()))
logger.info("Done.")
