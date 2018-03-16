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

#include "SectionPerfcounter.h"
#include "Environment.h"
#include "Logger.h"
#include "PerfCounter.h"
#include "PerfCounterCommon.h"
#include "stringutil.h"

int NameBaseNumberMap::getCounterBaseNumber(const std::string &counterName) {
    // Fill name -> counter ID maps lazily when first needed.
    if (_nameIdMaps.empty()) {
        _nameIdMaps = {perf_name_map<char>(_winapi, false),
                       perf_name_map<char>(_winapi, true)};
    }

    for (const auto &nameIdMap : _nameIdMaps) {
        const auto it = nameIdMap.find(counterName);

        if (it != nameIdMap.end()) {
            return it->second;
        }
    }
    Debug(_logger) << "NameBaseNumberMap::getCounterBaseNumber "
                   << "could not resolve counter name " << counterName;
    return -1;
}

SectionPerfcounter::SectionPerfcounter(const std::string &outputName,
                                       const std::string &configName,
                                       const Environment &env,
                                       NameBaseNumberMap &nameNumberMap,
                                       Logger *logger,
                                       const WinApiAdaptor &winapi)
    : Section(outputName, configName, env, logger, winapi)
    , _nameNumberMap(nameNumberMap) {}

bool SectionPerfcounter::produceOutputInner(
    std::ostream &out, const std::optional<std::string> &) {
    Debug(_logger) << "SectionPerfcounter::produceOutputInner";
    try {
        const int counterBaseNumber =
            _nameNumberMap.getCounterBaseNumber(_outputName);

        if (counterBaseNumber < 0) {
            return false;
        }

        PerfCounterObject counter_object(counterBaseNumber, _winapi, _logger);
        std::vector<std::wstring> instance_names =
            counter_object.instanceNames();
        std::vector<PERF_INSTANCE_DEFINITION *> instances =
            counter_object.instances();
        Debug(_logger) << "SectionPerfcounter::produceOutputInner: got "
                       << instance_names.size() << " instance names and "
                       << instances.size() << " instances.";
        // we have to transpose the data coming from the perfcounter
        std::map<int, std::vector<std::wstring>> value_map;

        for (size_t i = 0; i < instances.size(); ++i) {
            value_map[i] = std::vector<std::wstring>();
        }

        for (const auto &counter : counter_object.counters()) {
            int idx = 0;
            for (ULONGLONG value : counter.values(instances)) {
                value_map[idx++].push_back(std::to_wstring(value));
            }
        }

        out << "instance," << Utf8(join(counter_object.counterNames(), L","))
            << "\n";
        for (const auto & [ index, values ] : value_map) {
            std::wstring instance_name = L"\"\"";
            if (static_cast<size_t>(index) < instance_names.size()) {
                instance_name = instance_names[index];
            }
            out << Utf8(instance_name) << "," << Utf8(join(values, L","))
                << "\n";
        }
    } catch (const std::exception &e) {
        Error(_logger) << "Exception: " << e.what();
        return false;
    }
    return true;
}
