#!/usr/bin/env python
# -*- encoding: utf-8; py-indent-offset: 4 -*-
# +------------------------------------------------------------------+
# |             ____ _               _        __  __ _  __           |
# |            / ___| |__   ___  ___| | __   |  \/  | |/ /           |
# |           | |   | '_ \ / _ \/ __| |/ /   | |\/| | ' /            |
# |           | |___| | | |  __/ (__|   <    | |  | | . \            |
# |            \____|_| |_|\___|\___|_|\_\___|_|  |_|_|\_\           |
# |                                                                  |
# | Copyright Mathias Kettner 2014             mk@mathias-kettner.de |
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

"""Performing the actual checks."""

import os
import signal
import tempfile
import time

import cmk
import cmk.defines as defines
import cmk.tty as tty
import cmk.cpu_tracking as cpu_tracking
from cmk.exceptions import MKGeneralException

import cmk_base.utils
import cmk_base.console as console
import cmk_base.config as config
import cmk_base.checks as checks
import cmk_base.snmp as snmp
import cmk_base.data_sources as data_sources
import cmk_base.item_state as item_state
import cmk_base.core as core
import cmk_base.check_table as check_table
from cmk_base.exceptions import MKTimeout, MKSkipCheck, MKAgentError, \
                                MKSNMPError, MKParseFunctionError

try:
    import cmk_base.cee.keepalive as keepalive
except ImportError:
    keepalive = None

# global variables used to cache temporary values that do not need
# to be reset after a configuration change.
_nagios_command_pipe   = None # Filedescriptor to open nagios command pipe.
_checkresult_file_fd   = None
_checkresult_file_path = None

_submit_to_core = True
_show_perfdata  = False

#.
#   .--Checking------------------------------------------------------------.
#   |               ____ _               _    _                            |
#   |              / ___| |__   ___  ___| | _(_)_ __   __ _                |
#   |             | |   | '_ \ / _ \/ __| |/ / | '_ \ / _` |               |
#   |             | |___| | | |  __/ (__|   <| | | | | (_| |               |
#   |              \____|_| |_|\___|\___|_|\_\_|_| |_|\__, |               |
#   |                                                 |___/                |
#   +----------------------------------------------------------------------+
#   | Execute the Check_MK checks on hosts                                 |
#   '----------------------------------------------------------------------'

# This is the main check function - the central entry point
def do_check(hostname, ipaddress, only_check_types=None):
    cpu_tracking.start("busy")
    console.verbose("Check_MK version %s\n" % cmk.__version__)

    expected_version = config.agent_target_version(hostname)

    # Exit state in various situations is configurable since 1.2.3i1
    exit_spec = config.exit_code_spec(hostname)

    try:
        item_state.load(hostname)
        cmk_info, num_success, missing_sections = \
            do_all_checks_on_host(hostname, ipaddress, only_check_types)

        agent_version = cmk_info["version"]
        agent_os = cmk_info.get("agentos")

        if _submit_to_core:
            item_state.save(hostname)

        # Add errors of problematic data sources to problems list
        problems = []
        for data_source, exceptions in data_sources.get_data_source_errors_of_host(hostname, ipaddress).items():
            for exc in exceptions:
                problems.append("%s" % exc)

        if problems:
            problems_txt = ", ".join(problems)
            output = "%s, " % problems_txt

            if problems_txt == "Empty output from agent":
                status = exit_spec.get("empty_output", 2)
            else:
                status = exit_spec.get("connection", 2)

        elif missing_sections and num_success > 0:
            output = "Missing agent sections: %s - " % ", ".join(missing_sections)
            status = exit_spec.get("missing_sections", 1)

        elif missing_sections:
            output = "Got no information from host, "
            status = exit_spec.get("empty_output", 2)

        elif expected_version and agent_version \
             and not _is_expected_agent_version(agent_version, expected_version):
            # expected version can either be:
            # a) a single version string
            # b) a tuple of ("at_least", {'daily_build': '2014.06.01', 'release': '1.2.5i4'}
            #    (the dict keys are optional)
            if type(expected_version) == tuple and expected_version[0] == 'at_least':
                expected = 'at least'
                if 'daily_build' in expected_version[1]:
                    expected += ' build %s' % expected_version[1]['daily_build']
                if 'release' in expected_version[1]:
                    if 'daily_build' in expected_version[1]:
                        expected += ' or'
                    expected += ' release %s' % expected_version[1]['release']
            else:
                expected = expected_version
            output = "unexpected agent version %s (should be %s), " % (agent_version, expected)
            status = exit_spec.get("wrong_version", 1)

        elif config.agent_min_version and agent_version < config.agent_min_version:
            output = "old plugin version %s (should be at least %s), " % (agent_version, config.agent_min_version)
            status = exit_spec.get("wrong_version", 1)

        else:
            output = ""
            status = 0

        if not config.is_cluster(hostname) and agent_version != None:
            output += "Agent version %s, " % agent_version
        if not config.is_cluster(hostname) and agent_os != None:
            output += "Agent OS %s, " % agent_os

    except MKTimeout:
        raise

    except MKGeneralException, e:
        if cmk.debug.enabled():
            raise
        output = "%s, " % e
        status = exit_spec.get("exception", 3)

    if _checkresult_file_fd != None:
        _close_checkresult_file()

    cpu_tracking.end()
    phase_times = cpu_tracking.get_times()
    total_times = phase_times["TOTAL"]
    run_time = total_times[4]

    if config.check_mk_perfdata_with_times:
        output += "execution time %.1f sec|execution_time=%.3f user_time=%.3f "\
                  "system_time=%.3f children_user_time=%.3f children_system_time=%.3f" %\
                (run_time, run_time, total_times[0], total_times[1], total_times[2], total_times[3])

        for phase, times in phase_times.items():
            if phase in [ "agent", "snmp", "ds" ]:
                t = times[4] - sum(times[:4]) # real time - CPU time
                output += " cmk_time_%s=%.3f" % (phase, t)
        output += "\n"
    else:
        output += "execution time %.1f sec|execution_time=%.3f\n" % (run_time, run_time)

    if config.record_inline_snmp_stats and config.is_inline_snmp_host(hostname):
        import cmk_base.cee.inline_snmp
        cmk_base.cee.inline_snmp.save_snmp_stats()

    if _in_keepalive_mode():
        keepalive.add_keepalive_active_check_result(hostname, output)
        console.verbose(output)
    else:
        console.output(defines.short_service_state_name(status) + " - " + output.encode('utf-8'))

    return status


def _is_expected_agent_version(agent_version, expected_version):
    try:
        if agent_version in [ '(unknown)', None, 'None' ]:
            return False

        if type(expected_version) == str and expected_version != agent_version:
            return False

        elif type(expected_version) == tuple and expected_version[0] == 'at_least':
            spec = expected_version[1]
            if cmk_base.utils.is_daily_build_version(agent_version) and 'daily_build' in spec:
                expected = int(spec['daily_build'].replace('.', ''))

                branch = cmk_base.utils.branch_of_daily_build(agent_version)
                if branch == "master":
                    agent = int(agent_version.replace('.', ''))

                else: # branch build (e.g. 1.2.4-2014.06.01)
                    agent = int(agent_version.split('-')[1].replace('.', ''))

                if agent < expected:
                    return False

            elif 'release' in spec:
                if cmk_base.utils.is_daily_build_version(agent_version):
                    return False

                if cmk_base.utils.parse_check_mk_version(agent_version) \
                    < cmk_base.utils.parse_check_mk_version(spec['release']):
                    return False

        return True
    except Exception, e:
        if cmk.debug.enabled():
            raise
        raise MKGeneralException("Unable to check agent version (Agent: %s Expected: %s, Error: %s)" %
                (agent_version, expected_version, e))


# Loops over all checks for ANY host (cluster, real host), gets the data, calls the check
# function that examines that data and sends the result to the Core.
def do_all_checks_on_host(hostname, ipaddress, only_check_types=None, fetch_agent_version=True):
    cmk_info = { "version" : "(unknown)" }
    num_success, missing_sections = 0, set()

    checks.set_hostname(hostname)

    table = check_table.get_precompiled_check_table(hostname, remove_duplicates=True,
                                    world="active" if _in_keepalive_mode() else "config")

    sources = data_sources.DataSources(hostname)

    # When check types are specified via command line, enforce them. Otherwise use the
    # list of checks defined by the check table.
    if only_check_types is None:
        only_check_types = list(set([ e[0] for e in table ]))
    sources.enforce_check_types(only_check_types)

    # Gather the data from the sources
    all_host_infos = data_sources.get_host_infos(sources, hostname, ipaddress)

    for check_name, item, params, description in table:
        if only_check_types != None and check_name not in only_check_types:
            continue

        success = execute_check(all_host_infos, hostname, ipaddress, check_name, item, params, description)
        if success:
            num_success += 1
        else:
            # TODO: Is there a generic check_name -> info_name/section_name function?
            missing_sections.add(check_name.split('.')[0])

    if fetch_agent_version:
        if config.is_tcp_host(hostname):
            for line in data_sources.get_info_for_check(all_host_infos, hostname, ipaddress, "check_mk", for_discovery=False) or []:
                value = " ".join(line[1:]) if len(line) > 1 else None
                cmk_info[line[0][:-1].lower()] = value

        else:
            cmk_info["version"] = None
    else:
        cmk_info["version"] = None

    missing_section_list = sorted(list(missing_sections))

    return cmk_info, num_success, missing_section_list


def execute_check(all_host_infos, hostname, ipaddress, check_name, item, params, description):
    # Make a bit of context information globally available, so that functions
    # called by checks now this context
    checks.set_service(check_name, description)
    item_state.set_item_state_prefix(check_name, item)

    # Skip checks that are not in their check period
    period = config.check_period_of(hostname, description)
    if period and not core.check_timeperiod(period):
        console.verbose("Skipping service %s: currently not in timeperiod %s.\n" % (description, period))
        return False

    elif period:
        console.vverbose("Service %s: timeperiod %s is currently active.\n" % (description, period))

    info_type = check_name.split('.')[0]

    try:
        info = data_sources.get_info_for_check(all_host_infos, hostname, ipaddress, info_type, for_discovery=False)
    except MKParseFunctionError, e:
        x = e.exc_info()
        raise x[0], x[1], x[2] # re-raise the original exception to not destory the trace

    # TODO: Move this to a helper function
    if info is None: # No data for this check type
        return False

    # Can't do this here, because the parse functions can do anything with the data
    #assert type(info) in [ list, dict ]

    # In case of SNMP checks but missing agent response, skip this check.
    # Special checks which still need to be called even with empty data
    # may declare this.
    if not info and checks.is_snmp_check(check_name) \
       and not checks.check_info[check_name]["handle_empty_info"]:
        return False

    check_function = checks.check_info[check_name].get("check_function")
    if check_function is None:
        check_function = lambda item, params, info: (3, 'UNKNOWN - Check not implemented')

    dont_submit = False
    try:
        # Call the actual check function
        item_state.reset_wrapped_counters()

        raw_result = check_function(item, _determine_check_params(params), info)
        result = sanitize_check_result(raw_result, checks.is_snmp_check(check_name))

        item_state.raise_counter_wrap()

    except item_state.MKCounterWrapped, e:
        # handle check implementations that do not yet support the
        # handling of wrapped counters via exception on their own.
        # Do not submit any check result in that case:
        console.verbose("%-20s PEND - Cannot compute check result: %s\n" % (description, e))
        dont_submit = True

    except MKTimeout:
        raise

    except Exception, e:
        if cmk.debug.enabled():
            raise
        result = 3, cmk_base.crash_reporting.create_crash_dump(hostname, check_name, item,
                                    is_manual_check(hostname, check_name, item),
                                    params, description, info), []

    if not dont_submit:
        # Now add information about the age of the data in the agent
        # sections. This is in data_sources.g_agent_cache_info. For clusters we
        # use the oldest of the timestamps, of course.
        oldest_cached_at = None
        largest_interval = None

        def minn(a, b):
            if a == None:
                return b
            elif b == None:
                return a
            return min(a,b)

        for host_info in all_host_infos.values():
            section_entries = host_info.cache_info
            if info_type in section_entries:
                cached_at, cache_interval = section_entries[info_type]
                oldest_cached_at = minn(oldest_cached_at, cached_at)
                largest_interval = max(largest_interval, cache_interval)

        _submit_check_result(hostname, description, result,
                            cached_at=oldest_cached_at, cache_interval=largest_interval)
    return True


def _determine_check_params(params):
    if isinstance(params, dict) and "tp_default_value" in params:
        for timeperiod, tp_params in params["tp_values"]:
            tp_result = core.timeperiod_active(timeperiod)
            if tp_result == True:
                return tp_params
            elif tp_result == False:
                continue
            elif tp_result == None:
                # Connection error
                return params["tp_default_value"]
        else:
            return params["tp_default_value"]
    else:
        return params


def is_manual_check(hostname, check_type, item):
    manual_checks = check_table.get_check_table(hostname, remove_duplicates=True,
                                    world="active" if _in_keepalive_mode() else "config",
                                    skip_autochecks=True)
    return (check_type, item) in manual_checks


def sanitize_check_result(result, is_snmp):
    if type(result) == tuple:
        return _sanitize_tuple_check_result(result)

    elif result == None:
        return _item_not_found(is_snmp)

    else:
        return _sanitize_yield_check_result(result, is_snmp)


# The check function may return an iterator (using yield) since 1.2.5i5.
# This function handles this case and converts them to tuple results
def _sanitize_yield_check_result(result, is_snmp):
    subresults = list(result)

    # Empty list? Check returned nothing
    if not subresults:
        return _item_not_found(is_snmp)

    # Simple check with no separate subchecks (yield wouldn't have been neccessary here!)
    if len(subresults) == 1:
        state, infotext, perfdata = _sanitize_tuple_check_result(subresults[0], allow_missing_infotext=True)
        if infotext == None:
            return state, u"", perfdata
        else:
            return state, infotext, perfdata

    # Several sub results issued with multiple yields. Make that worst sub check
    # decide the total state, join the texts and performance data. Subresults with
    # an infotext of None are used for adding performance data.
    else:
        perfdata = []
        infotexts = []
        status = 0

        for subresult in subresults:
            st, text, perf = _sanitize_tuple_check_result(subresult, allow_missing_infotext=True)

            # FIXME/TODO: Why is the state only aggregated when having text != None?
            if text != None:
                infotexts.append(text + ["", "(!)", "(!!)", "(?)"][st])
                status = cmk_base.utils.worst_service_state(st, status)

            if perf != None:
                perfdata += subresult[2]

        return status, ", ".join(infotexts), perfdata


def _item_not_found(is_snmp):
    if is_snmp:
        return 3, "Item not found in SNMP data", []
    else:
        return 3, "Item not found in agent output", []


def _sanitize_tuple_check_result(result, allow_missing_infotext=False):
    if len(result) >= 3:
        state, infotext, perfdata = result[:3]
    else:
        state, infotext = result
        perfdata = None

    infotext = _sanitize_check_result_infotext(infotext, allow_missing_infotext)

    return state, infotext, perfdata


def _sanitize_check_result_infotext(infotext, allow_missing_infotext):
    if infotext == None and not allow_missing_infotext:
        raise MKGeneralException("Invalid infotext from check: \"None\"")

    if type(infotext) == str:
        return infotext.decode('utf-8')
    else:
        return infotext


def _convert_perf_data(p):
    # replace None with "" and fill up to 7 values
    p = (map(_convert_perf_value, p) + ['','','',''])[0:6]
    return "%s=%s;%s;%s;%s;%s" %  tuple(p)


def _convert_perf_value(x):
    if x == None:
        return ""
    elif type(x) in [ str, unicode ]:
        return x
    elif type(x) == float:
        return ("%.6f" % x).rstrip("0").rstrip(".")
    else:
        return str(x)


#.
#   .--Submit to core------------------------------------------------------.
#   |  ____        _               _ _     _                               |
#   | / ___| _   _| |__  _ __ ___ (_) |_  | |_ ___     ___ ___  _ __ ___   |
#   | \___ \| | | | '_ \| '_ ` _ \| | __| | __/ _ \   / __/ _ \| '__/ _ \  |
#   |  ___) | |_| | |_) | | | | | | | |_  | || (_) | | (_| (_) | | |  __/  |
#   | |____/ \__,_|_.__/|_| |_| |_|_|\__|  \__\___/   \___\___/|_|  \___|  |
#   |                                                                      |
#   +----------------------------------------------------------------------+
#   | Submit check results to the core. Care about different methods       |
#   | depending on the running core.                                       |
#   '----------------------------------------------------------------------'
# TODO: Put the core specific things to dedicated files

def _submit_check_result(host, servicedesc, result, cached_at=None, cache_interval=None):
    if not result:
        result = 3, "Check plugin did not return any result"

    if len(result) != 3:
        raise MKGeneralException("Invalid check result: %s" % (result, ))
    state, infotext, perfdata = result

    if not (
        infotext.startswith("OK -") or
        infotext.startswith("WARN -") or
        infotext.startswith("CRIT -") or
        infotext.startswith("UNKNOWN -")):
        infotext = defines.short_service_state_name(state) + " - " + infotext

    # make sure that plugin output does not contain a vertical bar. If that is the
    # case then replace it with a Uniocode "Light vertical bar
    if isinstance(infotext, unicode):
        # regular check results are unicode...
        infotext = infotext.replace(u"|", u"\u2758")
    else:
        # ...crash dumps, and hard-coded outputs are regular strings
        infotext = infotext.replace("|", u"\u2758".encode("utf8"))

    # performance data - if any - is stored in the third part of the result
    perftexts = []
    perftext = ""

    if perfdata:
        # Check may append the name of the check command to the
        # list of perfdata. It is of type string. And it might be
        # needed by the graphing tool in order to choose the correct
        # template. Currently this is used only by mrpe.
        if len(perfdata) > 0 and type(perfdata[-1]) in (str, unicode):
            check_command = perfdata[-1]
            del perfdata[-1]
        else:
            check_command = None

        for p in perfdata:
            perftexts.append(_convert_perf_data(p))

        if perftexts != []:
            if check_command and config.perfdata_format == "pnp":
                perftexts.append("[%s]" % check_command)
            perftext = "|" + (" ".join(perftexts))

    if _submit_to_core:
        _do_submit_to_core(host, servicedesc, state, infotext + perftext, cached_at, cache_interval)

    _output_check_result(servicedesc, state, infotext, perftexts)


def _output_check_result(servicedesc, state, infotext, perftexts):
    if _show_perfdata:
        infotext_fmt = "%-56s"
        p = ' (%s)' % (" ".join(perftexts))
    else:
        p = ''
        infotext_fmt = "%s"

    console.verbose("%-20s %s%s"+infotext_fmt+"%s%s\n",
        servicedesc.encode('utf-8'), tty.bold, tty.states[state],
        cmk_base.utils.make_utf8(infotext.split('\n')[0]),
        tty.normal, cmk_base.utils.make_utf8(p))


def _do_submit_to_core(host, service, state, output, cached_at = None, cache_interval = None):
    if _in_keepalive_mode():
        # Regular case for the CMC - check helpers are running in keepalive mode
        keepalive.add_keepalive_check_result(host, service, state, output, cached_at, cache_interval)

    elif config.check_submission == "pipe" or config.monitoring_core == "cmc":
        # In case of CMC this is used when running "cmk" manually
        _submit_via_command_pipe(host, service, state, output)

    elif config.check_submission == "file":
        _submit_via_check_result_file(host, service, state, output)

    else:
        raise MKGeneralException("Invalid setting %r for check_submission. "
                                 "Must be 'pipe' or 'file'" % config.check_submission)


def _submit_via_check_result_file(host, service, state, output):
    output = output.replace("\n", "\\n")
    _open_checkresult_file()
    if _checkresult_file_fd:
        now = time.time()
        os.write(_checkresult_file_fd,
                """host_name=%s
service_description=%s
check_type=1
check_options=0
reschedule_check
latency=0.0
start_time=%.1f
finish_time=%.1f
return_code=%d
output=%s

""" % (host, cmk_base.utils.make_utf8(service), now, now,
       state, cmk_base.utils.make_utf8(output)))


def _open_checkresult_file():
    global _checkresult_file_fd
    global _checkresult_file_path
    if _checkresult_file_fd == None:
        try:
            _checkresult_file_fd, _checkresult_file_path = \
                tempfile.mkstemp('', 'c', cmk.paths.check_result_path)
        except Exception, e:
            raise MKGeneralException("Cannot create check result file in %s: %s" %
                    (cmk.paths.check_result_path, e))


def _close_checkresult_file():
    global _checkresult_file_fd
    if _checkresult_file_fd != None:
        os.close(_checkresult_file_fd)
        file(_checkresult_file_path + ".ok", "w")
        _checkresult_file_fd = None


def _submit_via_command_pipe(host, service, state, output):
    output = output.replace("\n", "\\n")
    _open_command_pipe()
    if _nagios_command_pipe:
        # [<timestamp>] PROCESS_SERVICE_CHECK_RESULT;<host_name>;<svc_description>;<return_code>;<plugin_output>
        _nagios_command_pipe.write("[%d] PROCESS_SERVICE_CHECK_RESULT;%s;%s;%d;%s\n" %
                               (int(time.time()), host,
                                cmk_base.utils.make_utf8(service),
                                state,
                                cmk_base.utils.make_utf8(output)))
        # Important: Nagios needs the complete command in one single write() block!
        # Python buffers and sends chunks of 4096 bytes, if we do not flush.
        _nagios_command_pipe.flush()


def _open_command_pipe():
    global _nagios_command_pipe
    if _nagios_command_pipe == None:
        if not os.path.exists(cmk.paths.nagios_command_pipe_path):
            _nagios_command_pipe = False # False means: tried but failed to open
            raise MKGeneralException("Missing core command pipe '%s'" % cmk.paths.nagios_command_pipe_path)
        else:
            try:
                signal.signal(signal.SIGALRM, _core_pipe_open_timeout)
                signal.alarm(3) # three seconds to open pipe
                _nagios_command_pipe =  file(cmk.paths.nagios_command_pipe_path, 'w')
                signal.alarm(0) # cancel alarm
            except Exception, e:
                _nagios_command_pipe = False
                raise MKGeneralException("Error writing to command pipe: %s" % e)


def _core_pipe_open_timeout(signum, stackframe):
    raise IOError("Timeout while opening pipe")

#.
#   .--Misc----------------------------------------------------------------.
#   |                          __  __ _                                    |
#   |                         |  \/  (_)___  ___                           |
#   |                         | |\/| | / __|/ __|                          |
#   |                         | |  | | \__ \ (__                           |
#   |                         |_|  |_|_|___/\___|                          |
#   |                                                                      |
#   +----------------------------------------------------------------------+
#   | Various helper functions                                             |
#   '----------------------------------------------------------------------'

def show_perfdata():
    global _show_perfdata
    _show_perfdata = True


def disable_submit():
    global _submit_to_core
    _submit_to_core = False


def _in_keepalive_mode():
    return keepalive and keepalive.enabled()
