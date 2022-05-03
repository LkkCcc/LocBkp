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
import shutil
import subprocess
from datetime import datetime, timedelta
import tempfile
import os

from locbkp.utils.dictionary import BACKUP_LIST, DESTINATION_DIRECTORY

from locbkp.utils.utils import sanitize_path, get_tree, get_config, progress_bar, get_dir_size_mb, get_logger

if os.name == "nt":
    p7z_path = "C:\\Program Files\\7-Zip\\7z.exe"
else:
    p7z_path = "/usr/bin/7z"


class Backup:
    def __init__(self, backup_list_path):
        self.version = "0.0.4j"
        self.backup_list_path = backup_list_path
        self.backup_list_name = sanitize_path(*os.path.basename(backup_list_path).split(".")[:-1])
        self.time_start = datetime.now()
        self.time_preparation = timedelta(seconds=0)
        self.time_preparation_finished = self.time_start
        self.time_copy_temp = timedelta(seconds=0)
        self.time_copy_temp_finished = self.time_start
        self.time_compress = timedelta(seconds=0)
        self.time_compress_finished = self.time_start
        self.time_transfer = timedelta(seconds=0)
        self.time_transfer_finished = self.time_start
        self.time_cleanup = timedelta(seconds=0)
        self.time_cleanup_finished = self.time_start
        self.files_backed = []
        self.dirs_backed = []
        self.size_before_compression = 0.0
        self.size_after_compression = 0.0
        self.curdate = self.time_start.strftime("%d-%m-%Y_%H.%M.%S")
        self.temp = tempfile.gettempdir()
        self.packing_directory = sanitize_path(self.temp, "{}_{}".format(self.backup_list_name, self.curdate))
        self.logger = get_logger()
        try:
            os.makedirs(self.packing_directory)
        except BaseException as e:
            self.logger.error("Could not create temp directory: {}. Cannot proceed.".format(e.__class__.__name__))
        self.logfile = sanitize_path(self.temp, "LocBkp_{}_{}.log".format(self.backup_list_name, self.curdate))
        self.archive_name = "backup_{}.7z".format(self.curdate)
        self.archive_path = sanitize_path(self.temp, self.archive_name)
        self.logger = get_logger(name="LocBkp({})".format(self.backup_list_name), logpath=self.logfile)
        self.logger.info("LocBkp v.{} Backup instance initialized.".format(self.version))
        self.backup_list = get_config(backup_list_path)

    def prepare_backup_lists(self, backup_list):
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

    def start_backup(self):
        files, dirs = self.prepare_backup_lists(self.backup_list[BACKUP_LIST])
        self.time_preparation_finished = datetime.now()
        self.time_preparation = self.time_preparation_finished - self.time_start
        self.backup(self.backup_list[DESTINATION_DIRECTORY], files, dirs)

    def backup(self, destdir, files, dirs):
        self.logger.info("Creating directory structure...")
        self.logger.info("Will create {} directories...".format(len(dirs)))
        self.backup_empty_dirs(dirs)

        self.logger.info("Backing up {} files to {}...".format(len(files), self.packing_directory))
        self.backup_files(files)
        self.logger.info("Done backing up files.")
        self.time_copy_temp_finished = datetime.now()
        self.time_copy_temp = self.time_copy_temp_finished - self.time_preparation_finished
        self.backup_finalize(destdir)

    def generate_backup_report(self, backup_size):
        try:
            with open(sanitize_path(self.packing_directory, "LocBkp_report_{}.json".format(self.curdate)),
                      "w") as locbkp_report:
                json.dump(
                    {
                        "files_backed": self.files_backed,
                        "dirs_backed": self.dirs_backed,
                        "size_uncompressed_mb": backup_size
                    },
                    locbkp_report,
                    indent=4
                )
        except BaseException as e:
            self.logger.error("Could not create backup report! Error: {}".format(e.__class__.__name__))

    def backup_empty_dirs(self, dirlist):
        for adir in dirlist:
            final_path = sanitize_path(self.packing_directory, adir)
            try:
                # logger.info("Backing up directory structure: {} to {}".format(adir, final_path))
                os.makedirs(final_path)
                self.dirs_backed.append(adir)
            except FileExistsError:
                pass
            except BaseException as e:
                self.logger.warning("Could not create a directory {}: {}".format(final_path, e.__class__.__name__))

    def backup_files(self, fileslist):
        total_files = len(fileslist)
        for num, afile in enumerate(fileslist):
            progress_bar(num, total_files)
            if os.path.exists(afile) and os.path.isfile(afile):
                if self.backup_file(afile):
                    self.files_backed.append(sanitize_path(afile, self.packing_directory))

    def backup_finalize(self, destdir):
        self.logger.info("Backup finished. Finalizing...")
        self.size_before_compression = get_dir_size_mb(self.packing_directory)
        self.logger.info("Backed up {:.3f}Mb of data.".format(self.size_before_compression))
        self.logger.info("Generating backup report...")
        self.generate_backup_report(self.size_before_compression)
        self.logger.info("Compressing backup...")
        time_pre_compress = datetime.now()
        self.compress_backup()
        self.time_compress_finished = datetime.now()
        self.time_compress = self.time_compress_finished - time_pre_compress
        size_after_compression = os.path.getsize(self.archive_path) / 1024 / 1024
        self.logger.info("Backup is compressed. Compressed size is {:.3f}Mb".format(size_after_compression))
        self.transfer_file(destdir)
        self.logger.info("Done. Cleaning up...")
        os.remove(self.archive_path)
        shutil.rmtree(self.packing_directory)
        os.remove(self.logfile)
        self.logger.info("Cleaned up.")
        self.time_cleanup_finished = datetime.now()
        self.time_cleanup = self.time_cleanup_finished - self.time_transfer_finished

    def compress_backup(self):
        p7z_cmd = [p7z_path, "a", "-t7z", self.archive_path, "-mx9", "-aoa", self.packing_directory]
        self.logger.info("Executing: {}".format(" ".join(p7z_cmd)))
        try:
            process = subprocess.run(p7z_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)
        except BaseException as e:
            self.logger.error("Could not compress backup: {}".format(e.__class__.__name__))
            self.logger.error("Process stdout: {}".format(process.stdout))

    def transfer_file(self, path_to):
        self.logger.info("Transferring backup to destination location...")
        time_pre_transfer = datetime.now()
        destfile = sanitize_path(path_to, self.archive_name)
        try:
            shutil.copy(self.archive_path, destfile)
        except BaseException as e:
            self.logger.error("Could not transfer backup to {}: {}".format(destfile, e.__class__.__name__))
        self.time_transfer_finished = datetime.now()
        self.time_transfer = self.time_transfer_finished - time_pre_transfer

    def backup_file(self, file_path):
        destination = sanitize_path(self.packing_directory, file_path)
        # logger.info("Backing up {} to {}".format(file_path, destination))
        try:
            shutil.copy(file_path, destination)
        except BaseException as e:
            self.logger.warning("Could not copy {} to {}: {}".format(file_path, destination, e.__class__.__name__))
        return True

    def start(self):
        self.start_backup()
        total_time = datetime.now() - self.time_start
        self.logger.info("Backed up {} files and {} directories.".format(len(self.files_backed), len(self.dirs_backed)))
        self.logger.info(
            "Time: Preparation: {:.3f}s; Copy: {:.3f}s; Compress: {:.3f}s; Transfer: {:.3f}s; Cleanup: {:3f}s."
            .format(self.time_preparation.total_seconds(), self.time_copy_temp.total_seconds(),
                    self.time_compress.total_seconds(),
                    self.time_transfer.total_seconds(), self.time_cleanup.total_seconds()))
        self.logger.info("Compression effectiveness is {:.2f}%".format(
            100 - (self.size_after_compression / self.size_before_compression) * 100))
        self.logger.info("Total time is {:.3f}s.".format(total_time.total_seconds()))
        self.logger.info("Done.")
