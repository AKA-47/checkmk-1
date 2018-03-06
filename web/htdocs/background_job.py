#!/usr/bin/env python
# -*- encoding: utf-8; py-indent-offset: 4 -*-
# +------------------------------------------------------------------+
# |             ____ _               _        __  __ _  __           |
# |            / ___| |__   ___  ___| | __   |  \/  | |/ /           |
# |           | |   | '_ \ / _ \/ __| |/ /   | |\/| | ' /            |
# |           | |___| | | |  __/ (__|   <    | |  | | . \            |
# |            \____|_| |_|\___|\___|_|\_\___|_|  |_|_|\_\           |
# |                                                                  |
# | Copyright Mathias Kettner 2016             mk@mathias-kettner.de |
# +------------------------------------------------------------------+
#
# This file is part of Check_MK.
# The official homepage is at http://mathias-kettner.de/check_mk.
#
# check_mk is free software;  you can redistribute it and/or modify it
# under the  terms of the  GNU General Public License  as published by
# the Free Software Foundation in version 2.  check_mk is  distributed
# in the hope that it will be useful, but WITHOUT ANY WARRANTY;  with-
# out even the implied warranty of  MERCHANTABILITY  or  FITNESS FOR A
# PARTICULAR PURPOSE. See the  GNU General Public License for more de-
# tails. You should have  received  a copy of the  GNU  General Public
# License along with GNU Make; see the file  COPYING.  If  not,  write
# to the Free Software Foundation, Inc., 51 Franklin St,  Fifth Floor,
# Boston, MA 02110-1301 USA.


import os
import sys
import time
import pprint
import threading
import multiprocessing
from cStringIO import StringIO

import cmk
import cmk.log
import cmk.store as store
import psutil
import shutil
import signal
import traceback
from cmk.exceptions import MKGeneralException

#.
#   .--Function Interface--------------------------------------------------.
#   |               _____                 _   _                            |
#   |              |  ___|   _ _ __   ___| |_(_) ___  _ __                 |
#   |              | |_ | | | | '_ \ / __| __| |/ _ \| '_ \                |
#   |              |  _|| |_| | | | | (__| |_| | (_) | | | |               |
#   |              |_|   \__,_|_| |_|\___|\__|_|\___/|_| |_|               |
#   |                                                                      |
#   |              ___       _             __                              |
#   |             |_ _|_ __ | |_ ___ _ __ / _| __ _  ___ ___               |
#   |              | || '_ \| __/ _ \ '__| |_ / _` |/ __/ _ \              |
#   |              | || | | | ||  __/ |  |  _| (_| | (_|  __/              |
#   |             |___|_| |_|\__\___|_|  |_|  \__,_|\___\___|              |
#   |                                                                      |
#   +----------------------------------------------------------------------+

class BackgroundProcessInterface(object):
    progress_update_message = "JobProgressUpdate"
    result_message          = "JobResult"
    exception_message       = "JobException"

    def __init__(self, job_parameters):
        super(BackgroundProcessInterface, self).__init__()
        self._job_parameters = job_parameters


    def get_work_dir(self):
        return self._job_parameters["work_dir"]


    def get_job_id(self):
        return self._job_parameters["job_id"]


    def get_logger(self):
        return self._job_parameters["logger"]


    @classmethod
    def send_progress_update(cls, info):
        print "%s:%s" % (cls.progress_update_message, info)


    @classmethod
    def send_result_message(cls, info):
        print "%s:%s" % (cls.result_message, info)


    @classmethod
    def send_exception(cls, info):
        # Exceptions get an extra newline
        # Some error messages tend not output a \n at the end..
        print "\n%s:%s" % (cls.exception_message, info)


    @classmethod
    def parse_progress_info(cls, progress_info_rawdata):
        response = {cls.progress_update_message: [],
                    cls.result_message         : [],
                    cls.exception_message      : []}


        def finalize_last_block():
            if not message_block:
                return
            response[current_message_type].append(message_block)

        lines = progress_info_rawdata.splitlines()
        current_message_type = cls.progress_update_message
        message_block = ""
        for line in lines:
            for message_type in response.keys():
                if line.startswith(message_type):
                    finalize_last_block()
                    current_message_type = message_type
                    message_block = line[len(message_type)+1:]
                    break
            else:
                message_block += "\n%s" % line
        finalize_last_block()
        return response


#.
#   .--Background Process--------------------------------------------------.
#   |       ____             _                                   _         |
#   |      | __ )  __ _  ___| | ____ _ _ __ ___  _   _ _ __   __| |        |
#   |      |  _ \ / _` |/ __| |/ / _` | '__/ _ \| | | | '_ \ / _` |        |
#   |      | |_) | (_| | (__|   < (_| | | | (_) | |_| | | | | (_| |        |
#   |      |____/ \__,_|\___|_|\_\__, |_|  \___/ \__,_|_| |_|\__,_|        |
#   |                            |___/                                     |
#   |                  ____                                                |
#   |                 |  _ \ _ __ ___   ___ ___  ___ ___                   |
#   |                 | |_) | '__/ _ \ / __/ _ \/ __/ __|                  |
#   |                 |  __/| | | (_) | (_|  __/\__ \__ \                  |
#   |                 |_|   |_|  \___/ \___\___||___/___/                  |
#   |                                                                      |
#   +----------------------------------------------------------------------+
#   | When started, BackgroundJob spawns one instance of BackgroundProcess |
#   '----------------------------------------------------------------------'

class BackgroundProcess(multiprocessing.Process):
    def __init__(self, job_parameters):
        super(BackgroundProcess, self).__init__()
        self._job_parameters = job_parameters
        self._jobstatus      = self._job_parameters["jobstatus"]
        self._logger         = None # the logger is initialized in the run function
        signal.signal(signal.SIGTERM, self._exit)


    def _exit(self, signum, frame):
        self._jobstatus.update_status({"state": JobStatus.state_stopped})
        os._exit(0)


    def run(self):
        # Detach from parent (apache) -> Remain running when apache is restarted
        os.setsid()

        import cmk.daemon as daemon
        daemon.set_procname(BackgroundJobDefines.process_name)

        # Close file descpriptors. This also closes logfile handles!
        self._close_fds()

        ##################### ALL HANDLES HAVE BEEN CLOSED BOUNDARY ###########################

        # Setup environment (Logging, Livestatus handles, etc.)
        try:
            self.initialize_environment()
            self._jobstatus.update_status({"progress_info": BackgroundProcessInterface.parse_progress_info(""),
                                           "state": JobStatus.state_running})

            # The actual function call
            self._execute_function()
        except Exception, e:
            exception_message = "%s:Exception while preparing background function environment: %s" %\
                                (BackgroundProcessInterface.exception_message, traceback.format_exc())
            progress_info     = BackgroundProcessInterface.parse_progress_info(exception_message)
            self._jobstatus.update_status({"progress_info": progress_info,
                                           "state": JobStatus.state_exception})



    def _close_fds(self):
        try:
            MAXFD = os.sysconf("SC_OPEN_MAX")
        except:
            MAXFD = 256

        # Close all filedescriptors, except stdin/stdout
        os.closerange(3, MAXFD)


    def initialize_environment(self):
        if not self._logger:
            self._logger = cmk.log.logger

        self._job_parameters["logger"] = self._logger

        # Solely used for process identification
        self._jobstatus.open_statusfile_handle()


    def _execute_function(self):
        # The specific function is called in a separate thread
        # The main thread collects the stdout from the function-thread and updates the status file accordingly
        sys.stdout = StringIO()
        t = threading.Thread(target=self._call_function_with_exception_handling, args=[self._job_parameters])
        t.start()

        last_progress_info = ""
        while t.isAlive():
            time.sleep(0.2)
            progress_info = sys.stdout.getvalue() # pylint: disable=no-member
            if progress_info != last_progress_info:
                self._jobstatus.update_status({"progress_info": BackgroundProcessInterface.parse_progress_info(progress_info)})
                last_progress_info = progress_info
        t.join()

        # Final progress info update
        job_status_update = {}
        progress_info = sys.stdout.getvalue() # pylint: disable=no-member

        if progress_info != last_progress_info:
             job_status_update.update({"progress_info": BackgroundProcessInterface.parse_progress_info(progress_info)})

        # Final status message update
        job_status = self._jobstatus.get_status()
        if job_status.get("progress_info", {}).get("JobException"):
            final_state = JobStatus.state_exception
        else:
            final_state = JobStatus.state_finished

        job_status_update.update({"state": final_state, "duration": time.time() - job_status["started"]})

        self._jobstatus.update_status(job_status_update)


    @staticmethod
    def _call_function_with_exception_handling(job_parameters):
        func_ptr, args, kwargs = job_parameters["function_parameters"]
        job_interface = BackgroundProcessInterface(job_parameters)

        if "job_interface" in func_ptr.func_code.co_varnames:
            kwargs["job_interface"] = job_interface

        try:
            func_ptr(*args, **kwargs)
        except Exception, e:
            logger = job_interface.get_logger()
            logger.error("Exception in background function:\n%s" % (traceback.format_exc()))
            job_interface.send_exception(_("Exception: %s") % (e))



class BackgroundJobDefines(object):
    base_dir = os.path.join(cmk.paths.var_dir, "background_jobs")
    process_name = "cmk-job" # NOTE: keep this name short! psutil.Process tends to truncate long names



#.
#   .--Background Job------------------------------------------------------.
#   |       ____             _                                   _         |
#   |      | __ )  __ _  ___| | ____ _ _ __ ___  _   _ _ __   __| |        |
#   |      |  _ \ / _` |/ __| |/ / _` | '__/ _ \| | | | '_ \ / _` |        |
#   |      | |_) | (_| | (__|   < (_| | | | (_) | |_| | | | | (_| |        |
#   |      |____/ \__,_|\___|_|\_\__, |_|  \___/ \__,_|_| |_|\__,_|        |
#   |                            |___/                                     |
#   |                              _       _                               |
#   |                             | | ___ | |__                            |
#   |                          _  | |/ _ \| '_ \                           |
#   |                         | |_| | (_) | |_) |                          |
#   |                          \___/ \___/|_.__/                           |
#   |                                                                      |
#   +----------------------------------------------------------------------+
#   |                                                                      |
#   '----------------------------------------------------------------------'

class BackgroundJob(object):
    _background_process_class = BackgroundProcess
    housekeeping_max_age_sec = 86400 * 30
    housekeeping_max_count   = 50

    _
    def __init__(self, job_id, logger=None, **kwargs):
        super(BackgroundJob, self).__init__()
        self._job_id             = job_id
        self._job_base_dir       = BackgroundJobDefines.base_dir

        if not logger:
            raise MKGeneralException(_("The background job is missing a logger instance"))
        self._logger = logger

        kwargs.setdefault("stoppable", True)

        self._kwargs       = kwargs
        self._work_dir     = os.path.join(self._job_base_dir, self._job_id)
        self._jobstatus    = JobStatus(os.path.join(self._work_dir, "jobstatus.mk"))

        # The function ptr and its args/kwargs
        self._queued_function = None


    def get_job_id(self):
        return self._job_id


    def get_title(self):
        return self._jobstatus.get_status().get("title", _("Background job"))


    def get_work_dir(self):
        return self._work_dir


    def exists(self):
        return os.path.exists(self._work_dir) and self._jobstatus.statusfile_exists()


    def is_available(self):
        return self.exists()


    def is_stoppable(self):
        return self._jobstatus.get_status().get("stoppable", True) == True


    def is_running(self):
        if not self.exists():
            return False

        job_status = self.get_status()

        if job_status["state"] == JobStatus.state_finished:
            return False

        if "pid" in job_status:
            try:
                p = psutil.Process(job_status["pid"])
                if job_status["state"] == JobStatus.state_initialized:
                    # The process was just created, but has/may not been renamed yet
                    # Additionally it has no open file handle to the status file
                    # The _is_correct_process check will fail in this gray area
                    # We consider this scenario as OK, if the start time was recent enough
                    if time.time() - job_status["started"] < 5: # 5 seconds
                        return True

                if self._is_correct_process(job_status, p):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                return False

        return False


    def update_status(self, new_data):
        self._jobstatus.update_status(new_data)


    def stop(self):
        if not self.is_running():
            raise MKGeneralException(_("Job already finished"))

        if not self.is_stoppable():
            raise MKGeneralException(_("This job cannot be stopped"))

        self._terminate_processes()

        job_status = self._jobstatus.get_status()
        duration = time.time() - job_status["started"]
        self._jobstatus.update_status({"state": self._jobstatus.state_stopped, "duration": duration})



    def delete(self):
        if not self.is_stoppable() and self.is_running():
            raise MKGeneralException(_("Cannot delete job. Job cannot be stopped."))

        self._terminate_processes()

        if os.path.exists(self._work_dir):
            shutil.rmtree(self._work_dir)


    def _terminate_processes(self):
        job_status = self.get_status()

        if not job_status.get("pid"):
            return

        # Send SIGTERM
        try:
            process = psutil.Process(job_status["pid"])
            if not self._is_correct_process(job_status, process):
                return
            process.send_signal(signal.SIGTERM)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return


        # Give the jobs some time to terminate
        start_time = time.time()
        while time.time() - start_time < 10: # 10 seconds SIGTERM grace period
            job_still_running = False
            try:
                process = psutil.Process(job_status["pid"])
                if not self._is_correct_process(job_status, process):
                    return
                job_still_running = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return

            if not job_still_running:
                break
            time.sleep(0.1)



        # Kill unresponsive jobs
        # Send SIGKILL
        try:
            p = psutil.Process(job_status["pid"])
            if self._is_correct_process(job_status, process):
                p.send_signal(signal.SIGKILL)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return


    def _is_correct_process(self, job_status, psutil_process):
        if psutil_process.name() != BackgroundJobDefines.process_name:
            return False

        for openfile in psutil_process.open_files():
            if openfile.path.endswith(job_status["statusfile"]):
                return True

        return False


    def get_status(self):
        status = self._jobstatus.get_status()

        # Some dynamic stuff
        if status.get("state", "") == JobStatus.state_running:
            try:
                p = psutil.Process(status["pid"])
                if not self._is_correct_process(status, p):
                    status["state"] = JobStatus.state_stopped
                else:
                    status["duration"] = time.time() - status["started"]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                status["state"] = JobStatus.state_stopped

        return status


    def set_function(self, func_ptr, *args, **kwargs):
        self._queued_function = (func_ptr, args, kwargs)


    def start(self):
        if os.path.exists(self._work_dir):
            shutil.rmtree(self._work_dir)
        os.makedirs(self._work_dir)

        # Start processes
        self._jobstatus.update_status(self._kwargs)

        job_parameters = {}
        job_parameters["work_dir"]            = self._work_dir
        job_parameters["job_id"]              = self._job_id
        job_parameters["jobstatus"]           = self._jobstatus
        job_parameters["function_parameters"] = self._queued_function
        self._jobstatus.update_status({"state": JobStatus.state_initialized,
                                       "statusfile": os.path.join(self._job_id, "jobstatus.mk"),
                                       "started": time.time()})

        p = multiprocessing.Process(target=self._start_background_subprocess, args=[job_parameters])
        p.start()
        p.join()


    def _start_background_subprocess(self, job_parameters):
        try:
            p = self._background_process_class(job_parameters)
            p.start()
            self._jobstatus.update_status({"pid": p.pid})
        except Exception, e:
            self._logger.error("Error while starting subprocess: %s" % e)
        os._exit(0)



class JobStatus(object):
    state_initialized = "initialized"
    state_running     = "running"
    state_finished    = "finished"
    state_stopped     = "stopped"
    state_exception   = "exception"

    def __init__(self, job_statusfilepath):
        super(JobStatus, self).__init__()
        self._job_statusfilepath     = job_statusfilepath
        self._job_statusfile_handle  = None


    def get_status(self):
        return store.load_data_from_file(self._job_statusfilepath, {})


    def statusfile_exists(self):
        return os.path.exists(self._job_statusfilepath)


    def update_status(self, params):
        if not os.path.exists(os.path.dirname(self._job_statusfilepath)):
            return

        store.aquire_lock(self._job_statusfilepath)
        status = store.load_data_from_file(self._job_statusfilepath, {})
        status.update(params)
        store.save_mk_file(self._job_statusfilepath, self._format_value(status))
        store.release_lock(self._job_statusfilepath)


    def open_statusfile_handle(self):
        """
        This function creates a file handle which helps to uniquely identfiy the background process
        """
        self._job_statusfile_handle = open(self._job_statusfilepath, "r")


    def _format_value(self, value):
        return pprint.pformat(value)



class BackgroundJobManager(object):
    def __init__(self, logger):
        self._logger = logger.getChild("job_manager")
        super(BackgroundJobManager, self).__init__()


    # Checks for running jobs in the jobs default basedir
    def get_running_job_ids(self, job_class):
        all_jobs = self.get_all_job_ids(job_class)
        return [job_id for job_id in all_jobs if BackgroundJob(job_id, logger=self._logger).is_running()]


    # Checks for running jobs in the jobs default basedir
    def get_all_job_ids(self, job_class):
        job_ids = []
        if not os.path.exists(BackgroundJobDefines.base_dir):
            return job_ids

        for dirname in sorted(os.listdir(BackgroundJobDefines.base_dir)):
            if not dirname.startswith(job_class.job_prefix):
                continue
            job_ids.append(dirname)

        return job_ids


    def do_housekeeping(self, job_classes):
        try:
            for job_class in job_classes:
                job_ids = self.get_all_job_ids(job_class)
                max_age   = job_class.housekeeping_max_age_sec
                max_count = job_class.housekeeping_max_count
                all_jobs = []

                job_instances = {}
                for job_id in job_ids:
                    job_instances[job_id] = BackgroundJob(job_id, self._logger)
                    all_jobs.append((job_id, job_instances[job_id].get_status()))
                all_jobs.sort(key=lambda x: x[1]["started"], reverse=True)

                for entry in all_jobs[-1:0:-1]:
                    job_id, job_status = entry
                    if job_status["state"] == JobStatus.state_running:
                        continue

                    if len(all_jobs) > max_count or (time.time() - job_status["started"] > max_age):
                        job_instances[job_id].delete()
                        all_jobs.remove(entry)
        except Exception, e:
            self._logger.error(traceback.format_exc())

