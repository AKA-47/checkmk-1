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

#include "SectionCheckMK.h"
#include <cstring>
#include <iterator>
#include <string>
#include <vector>
#include "Environment.h"
#include "Logger.h"
#include "stringutil.h"

SectionCheckMK::SectionCheckMK(Configuration &config,
                               OnlyFromConfigurable &only_from,
                               script_statistics_t &script_statistics,
                               Logger *logger, const WinApiAdaptor &winapi)
    : Section("check_mk", "check_mk", config.getEnvironment(), logger, winapi)
    , _crash_debug(config, "global", "crash_debug", false, winapi)
    , _only_from(only_from)
    , _info_fields(createInfoFields())
    , _script_statistics(script_statistics) {}

std::vector<KVPair> SectionCheckMK::createInfoFields() const {
#ifdef ENVIRONMENT32
    const char *arch = "32bit";
#else
    const char *arch = "64bit";
#endif

    // common fields
    std::vector<KVPair> info_fields = {
        {"Version", CHECK_MK_VERSION},
        {"BuildDate", __DATE__},
        {"AgentOS", "windows"},
        {"Hostname", _env.hostname()},
        {"Architecture", arch},
        {"WorkingDirectory", _env.currentDirectory()},
        {"ConfigFile", configFileName(false, _env)},
        {"LocalConfigFile", configFileName(true, _env)},
        {"AgentDirectory", _env.agentDirectory()},
        {"PluginsDirectory", _env.pluginsDirectory()},
        {"StateDirectory", _env.stateDirectory()},
        {"ConfigDirectory", _env.configDirectory()},
        {"TempDirectory", _env.tempDirectory()},
        {"LogDirectory", _env.logDirectory()},
        {"SpoolDirectory", _env.spoolDirectory()},
        {"LocalDirectory", _env.localDirectory()}};

    return info_fields;
}

bool SectionCheckMK::produceOutputInner(std::ostream &out) {
    Debug(_logger) << "SectionCheckMK::produceOutputInner";
    // output static fields
    for (const auto &kv : _info_fields) {
        out << kv.first << ": " << kv.second << "\n";
    }

    out << "ScriptStatistics:"
        << " Plugin"
        << " C:" << _script_statistics["plugin_count"]
        << " E:" << _script_statistics["plugin_errors"]
        << " T:" << _script_statistics["plugin_timeouts"] << " Local"
        << " C:" << _script_statistics["local_count"]
        << " E:" << _script_statistics["local_errors"]
        << " T:" << _script_statistics["local_timeouts"] << "\n";

    // reset script statistics for next round
    _script_statistics.reset();

    out << "OnlyFrom:";
    // only from, isn't this static too?
    if (_only_from->size() == 0) {
        out << " 0.0.0.0/0\n";
    } else {
        for (const auto &is : *_only_from) {
            out << " " << is;
        }
    }
    return true;
}
