// +------------------------------------------------------------------+
// |             ____ _               _        __  __ _  __           |
// |            / ___| |__   ___  ___| | __   |  \/  | |/ /           |
// |           | |   | '_ \ / _ \/ __| |/ /   | |\/| | ' /            |
// |           | |___| | | |  __/ (__|   <    | |  | | . \            |
// |            \____|_| |_|\___|\___|_|\_\___|_|  |_|_|\_\           |
// |                                                                  |
// | Copyright Mathias Kettner 2017             mk@mathias-kettner.de |
// +------------------------------------------------------------------+
//
// This file is part of Check_MK.
// The official homepage is at http://mathias-kettner.de/check_mk.
//
// check_mk is free software;  you can redistribute it and/or modify it
// under the  terms of the  GNU General Public License  as published by
// the Free Software Foundation in version 2.  check_mk is  distributed
// in the hope that it will be useful, but WITHOUT ANY WARRANTY;  with-
// out even the implied warranty of  MERCHANTABILITY  or  FITNESS FOR A
// PARTICULAR PURPOSE. See the  GNU General Public License for more de-
// ails.  You should have  received  a copy of the  GNU  General Public
// License along with GNU Make; see the file  COPYING.  If  not,  write
// to the Free Software Foundation, Inc., 51 Franklin St,  Fifth Floor,
// Boston, MA 02110-1301 USA.

#include "ExternalCmd.h"
#include <shlwapi.h>
#include <cstring>
#include "Environment.h"
#include "Logger.h"
#include "WinApiAdaptor.h"
#include "types.h"
#include "win_error.h"

extern bool with_stderr;
extern HANDLE g_workers_job_object;

namespace {

const char *updater_exe = "cmk-update-agent.exe";

bool ends_with(std::string const &value, std::string const &ending) {
    if (ending.size() > value.size()) return false;
    return std::equal(ending.rbegin(), ending.rend(), value.rbegin());
}

std::string combinePaths(const std::string &path1, const std::string &path2,
                         const WinApiAdaptor &winapi) {
    std::vector<char> combined(MAX_PATH, '\0');
    return winapi.PathCombine(combined.data(), path1.c_str(), path2.c_str());
}

// Prepare cmk-update-agent.exe for being run in temp directory.
std::string handleAgentUpdater(Logger *logger, const WinApiAdaptor &winapi) {
    const auto *env = Environment::instance();
    if (env == nullptr) {
        const std::string errorMsg = "No environment!";
        Error(logger) << errorMsg;
        throw win_exception(winapi, errorMsg);
    }
    const auto source =
        combinePaths(env->pluginsDirectory(), updater_exe, winapi);
    const auto target = combinePaths(env->tempDirectory(), updater_exe, winapi);

    if (!winapi.CopyFile(source.c_str(), target.c_str(), false)) {
        std::string errorMsg = "copying ";
        errorMsg += source + " to " + target + " failed.";
        Error(logger) << errorMsg;
        throw AgentUpdaterError(errorMsg);
    }

    return target;
}

}  // namespace

std::string AgentUpdaterError::buildSectionCheckMK(
    const std::string &what) const {
    std::ostringstream oss("<<<check_mk>>>\nAgentUpdate: error ",
                           std::ios_base::ate);
    oss << what << std::endl;
    return oss.str();
}

ExternalCmd::ExternalCmd(const std::string &cmdline, const Environment &env,
                         Logger *logger, const WinApiAdaptor &winapi)
    : _script_stderr{winapi, INVALID_HANDLE_VALUE}
    , _script_stdout{winapi, INVALID_HANDLE_VALUE}
    , _process{INVALID_HANDLE_VALUE}
    , _job_object{INVALID_HANDLE_VALUE}
    , _stdout{winapi, INVALID_HANDLE_VALUE}
    , _stderr{winapi, INVALID_HANDLE_VALUE}
    , _logger(logger)
    , _winapi(winapi) {
    SECURITY_DESCRIPTOR security_descriptor;
    SECURITY_ATTRIBUTES security_attributes;
    // initialize security descriptor (Windows NT)
    if (env.isWinNt()) {
        _winapi.InitializeSecurityDescriptor(&security_descriptor,
                                             SECURITY_DESCRIPTOR_REVISION);
        _winapi.SetSecurityDescriptorDacl(&security_descriptor, true, nullptr,
                                          false);
        security_attributes.lpSecurityDescriptor = &security_descriptor;
    } else {
        security_attributes.lpSecurityDescriptor = nullptr;
    }

    security_attributes.nLength = sizeof(SECURITY_ATTRIBUTES);
    // child process needs to be able to inherit the pipe handles
    security_attributes.bInheritHandle = true;

    if (!_winapi.CreatePipe(_stdout.ptr(), _script_stdout.ptr(),
                            &security_attributes, 0)) {
        throw win_exception(_winapi, "failed to create pipe");
    }

    if (with_stderr) {
        if (!_winapi.CreatePipe(_stderr.ptr(), _script_stderr.ptr(),
                                &security_attributes, 0)) {
            throw win_exception(_winapi, "failed to create pipe");
        }
    }

    // base new process statup info on current process
    STARTUPINFO si;
    std::memset(&si, 0, sizeof(STARTUPINFO));
    si.cb = sizeof(STARTUPINFO);
    _winapi.GetStartupInfo(&si);
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    si.hStdOutput = (HANDLE)_script_stdout;
    si.hStdError =
        with_stderr ? (HANDLE)_script_stdout : (HANDLE)_script_stderr;

    bool detach_process = false;
    std::string actualCmd(cmdline);

    if (ends_with(cmdline, std::string(updater_exe) + "\"")) {
        detach_process = true;
        // Prepare cmk-update-agent.exe for being run in temp directory.
        actualCmd = handleAgentUpdater(logger, _winapi);
    }

    std::vector<char> cmdline_buf(actualCmd.cbegin(), actualCmd.cend());
    cmdline_buf.push_back('\0');

    DWORD dwCreationFlags = CREATE_NEW_CONSOLE;
    if (detach_process) {
        Debug(_logger) << "Detaching process: " << actualCmd << ", "
                       << detach_process;
        dwCreationFlags = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS;
    }

    PROCESS_INFORMATION pi;
    std::memset(&pi, 0, sizeof(PROCESS_INFORMATION));

    if (!_winapi.CreateProcess(nullptr, cmdline_buf.data(), nullptr, nullptr,
                               TRUE, dwCreationFlags, nullptr, nullptr, &si,
                               &pi)) {
        std::string errorMsg = "failed to spawn process " + actualCmd;
        if (detach_process) {
            throw AgentUpdaterError(errorMsg);
        } else {
            throw win_exception(winapi, errorMsg);
        }
    }

    _process = pi.hProcess;
    _winapi.CloseHandle(pi.hThread);

    // Create a job object for this process
    // Whenever the process ends all of its childs will terminate, too
    _job_object = _winapi.CreateJobObject(nullptr, nullptr);
    if (!detach_process) {
        _winapi.AssignProcessToJobObject(_job_object, pi.hProcess);
        _winapi.AssignProcessToJobObject(g_workers_job_object, pi.hProcess);
    }
}

ExternalCmd::~ExternalCmd() {
    if (_job_object != INVALID_HANDLE_VALUE) {
        _winapi.TerminateJobObject(_job_object, 1);
        _winapi.CloseHandle(_job_object);
    }
    _winapi.CloseHandle(_process);
}

void ExternalCmd::terminateJob(DWORD exit_code) {
    _winapi.TerminateJobObject(_job_object, exit_code);
    _winapi.CloseHandle(_job_object);
    _job_object = INVALID_HANDLE_VALUE;
}

DWORD ExternalCmd::exitCode() {
    DWORD res;
    _winapi.GetExitCodeProcess(_process, &res);
    return res;
}

DWORD ExternalCmd::stdoutAvailable() {
    DWORD available;
    _winapi.PeekNamedPipe((HANDLE)_stdout, nullptr, 0, nullptr, &available,
                          nullptr);
    return available;
}

DWORD ExternalCmd::stderrAvailable() {
    DWORD available;
    _winapi.PeekNamedPipe((HANDLE)_stderr, nullptr, 0, nullptr, &available,
                          nullptr);
    return available;
}

DWORD ExternalCmd::readStdout(char *buffer, size_t buffer_size, bool block) {
    return readPipe((HANDLE)_stdout, buffer, buffer_size, block);
}

DWORD ExternalCmd::readStderr(char *buffer, size_t buffer_size, bool block) {
    if (!with_stderr) {
        return readPipe((HANDLE)_stderr, buffer, buffer_size, block);
    } else {
        return 0;
    }
}

DWORD ExternalCmd::readPipe(HANDLE pipe, char *buffer, size_t buffer_size,
                            bool block) {
    DWORD bytes_read = 0UL;
    DWORD available = buffer_size;
    if (!block) {
        // avoid blocking by first peeking.
        _winapi.PeekNamedPipe(pipe, nullptr, 0, nullptr, &available, nullptr);
    }
    if (available > 0) {
        _winapi.ReadFile(pipe, buffer,
                         std::min<DWORD>(available, buffer_size - 1),
                         &bytes_read, nullptr);
        buffer[bytes_read] = '\0';
    }
    return bytes_read;
}
