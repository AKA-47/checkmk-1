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

#ifndef Thread_h
#define Thread_h

#include <winsock2.h>
#include <functional>
#include <memory>
#include <mutex>

class Environment;
class Logger;
class WinApiInterface;

struct ThreadData {
    ThreadData(const Environment &env_, Logger *logger_)
        : env(env_), logger(logger_) {}
    ThreadData(const ThreadData &) = delete;
    ThreadData &operator=(const ThreadData &) = delete;

    time_t push_until{0};
    bool terminate{false};
    const Environment &env;
    Logger *logger;
    bool new_request{false};
    sockaddr_storage last_address{0};
    std::mutex mutex;
};

class Thread {
public:
    using ThreadFunc = DWORD WINAPI (*)(void *);

public:
    // the caller keeps ownership
    template <typename T>
    Thread(ThreadFunc func, T &data, const WinApiInterface &winapi)
        : _func(func), _data(static_cast<void *>(&data)), _winapi(winapi) {}
    ~Thread();
    Thread(const Thread &) = delete;

    // wait for the thread to finish and return its exit code.
    // this will block if the thread hasn't finished already
    int join() const;
    void start();

    // return true if the thread was stated. If this is false,
    // a call to join would throw an exception
    bool wasStarted() const;

private:
    static void nop(void *) {}

    ThreadFunc _func;
    HANDLE _thread_handle{INVALID_HANDLE_VALUE};
    void *_data;
    const WinApiInterface &_winapi;
};

#endif  // Thread_h
