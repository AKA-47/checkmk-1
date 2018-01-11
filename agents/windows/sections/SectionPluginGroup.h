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

#ifndef SectionPluginGroup_h
#define SectionPluginGroup_h

#include <map>
#include <string>
#include "Configurable.h"
#include "Section.h"
#include "types.h"

class Environment;
class SectionPlugin;

// How single scripts are executed
enum script_execution_mode {
    SYNC,  // inline
    ASYNC  // delayed
};

// How delayed scripts are executed
enum script_async_execution { PARALLEL, SEQUENTIAL };

template <>
inline script_execution_mode from_string<script_execution_mode>(
    const WinApiAdaptor &, const std::string &value) {
    if (value == "async")
        return ASYNC;
    else if (value == "sync")
        return SYNC;
    throw std::runtime_error("invalid execution mode");
}

template <>
inline script_async_execution from_string<script_async_execution>(
    const WinApiAdaptor &, const std::string &value) {
    if (value == "parallel")
        return PARALLEL;
    else if (value == "sequential")
        return SEQUENTIAL;
    throw std::runtime_error("invalid async mode");
}

// States for plugin and local scripts
typedef enum _script_status {
    SCRIPT_IDLE,
    SCRIPT_FINISHED,
    SCRIPT_COLLECT,
    SCRIPT_ERROR,
    SCRIPT_TIMEOUT,
    SCRIPT_NONE,
} script_status;

typedef enum _script_type { PLUGIN, LOCAL, MRPE } script_type;

struct HeapBufferHandleTraits {
    using HandleT = char *;
    static HandleT invalidValue() { return nullptr; }

    static void closeHandle(HandleT value, const WinApiAdaptor &winapi) {
        winapi.HeapFree(winapi.GetProcessHeap(), 0, value);
    }
};

using HeapBufferHandle = WrappedHandle<HeapBufferHandleTraits>;

struct script_container {
    script_container(
        const std::string &_path,  // full path with interpreter, cscript, etc.
        const std::string &_script_path,  // path of script
        int _max_age, int _timeout, int _max_entries, const std::string &_user,
        script_type _type, script_execution_mode _execution_mode,
        const Environment &_env, Logger *_logger, const WinApiAdaptor &_winapi);

    script_container() = delete;
    script_container(const script_container &) = delete;
    ~script_container();
    script_container &operator=(const script_container &) = delete;

    const std::string path;         // full path with interpreter, cscript, etc.
    const std::string script_path;  // path of script
    const int max_age;
    const int timeout;
    const int max_retries;
    int retry_count{0};
    time_t buffer_time{0};
    HeapBufferHandle buffer;
    HeapBufferHandle buffer_work;
    const std::string run_as_user;
    const script_type type;
    const script_execution_mode execution_mode;
    script_status status{SCRIPT_IDLE};
    script_status last_problem{SCRIPT_NONE};
    volatile bool should_terminate{0};
    WrappedHandle<NullHandleTraits> worker_thread;
    DWORD exit_code{0};
    const Environment &env;
    Logger *logger;
    const WinApiAdaptor &winapi;
};

class SectionPluginGroup : public Section {
    friend DWORD
#if defined(_WIN32) || defined(_WIN64)
        __attribute__((__stdcall__))
#endif  // _WIN32 || _WIN64
        DataCollectionThread(LPVOID lpParam);

    typedef std::map<std::string, std::shared_ptr<script_container>>
        containers_t;

    static const int DEFAULT_PLUGIN_TIMEOUT = 60;
    static const int DEFAULT_LOCAL_TIMEOUT = 60;

    // Statistical values
    struct script_statistics_t {
        int count;
        int errors;
        int timeouts;
    } _script_stat;

public:
    SectionPluginGroup(Configuration &config, const std::string &path,
                       script_type type, Logger *logger,
                       const WinApiAdaptor &winapi,
                       const std::string &user = std::string());

    virtual ~SectionPluginGroup();

    virtual void startIfAsync() override;
    virtual void waitForCompletion() override;
    virtual std::vector<HANDLE> stopAsync() override;

protected:
    virtual bool produceOutputInner(std::ostream &out) override;

private:
    void collectData(script_execution_mode mode);
    void runContainer(script_container *cont);
    void outputContainers(std::ostream &out);

    void updateStatistics();

    bool exists(script_container *cont) const;
    bool fileInvalid(const char *filename) const;
    std::string deriveCommand(const char *filename) const;
    inline script_container *createContainer(const char *filename) const;
    void updateScripts();
    std::string withInterpreter(const char *path) const;

    int getTimeout(const char *name) const;
    int getCacheAge(const char *name) const;
    int getMaxRetries(const char *name) const;
    script_execution_mode getExecutionMode(const char *name) const;

    std::string _path;
    script_type _type;
    std::string _user;
    WrappedHandle<NullHandleTraits> _collection_thread;
    std::atomic<bool> _data_collection_retriggered{false};
    containers_t _containers;
    Configurable<script_execution_mode> _default_execution_mode;
    Configurable<script_async_execution> _async_execution;
    SplittingListConfigurable<
        std::vector<std::string>,
        BlockMode::BlockExclusive<std::vector<std::string>>>
        _execute_suffixes;
    KeyedListConfigurable<int> _timeout;
    KeyedListConfigurable<int> _cache_age;
    KeyedListConfigurable<int> _retry_count;
    KeyedListConfigurable<script_execution_mode> _execution_mode;
};

#endif  // SectionPluginGroup_h
