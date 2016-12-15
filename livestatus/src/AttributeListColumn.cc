// +------------------------------------------------------------------+
// |             ____ _               _        __  __ _  __           |
// |            / ___| |__   ___  ___| | __   |  \/  | |/ /           |
// |           | |   | '_ \ / _ \/ __| |/ /   | |\/| | ' /            |
// |           | |___| | | |  __/ (__|   <    | |  | | . \            |
// |            \____|_| |_|\___|\___|_|\_\___|_|  |_|_|\_\           |
// |                                                                  |
// | Copyright Mathias Kettner 2014             mk@mathias-kettner.de |
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
// tails. You should have  received  a copy of the  GNU  General Public
// License along with GNU Make; see the file  COPYING.  If  not,  write
// to the Free Software Foundation, Inc., 51 Franklin St,  Fifth Floor,
// Boston, MA 02110-1301 USA.

#include "AttributeListColumn.h"
#include <cctype>
#include <map>
#include <memory>
#include <ostream>
#include <utility>
#include <vector>
#include "Filter.h"
#include "IntFilter.h"
#include "Logger.h"
#include "Renderer.h"
#include "strutil.h"

using std::make_unique;
using std::map;
using std::string;
using std::to_string;
using std::unique_ptr;
using std::vector;

namespace {
map<string, unsigned long> known_attributes = {
    {"notifications_enabled", MODATTR_NOTIFICATIONS_ENABLED},
    {"active_checks_enabled", MODATTR_ACTIVE_CHECKS_ENABLED},
    {"passive_checks_enabled", MODATTR_PASSIVE_CHECKS_ENABLED},
    {"event_handler_enabled", MODATTR_EVENT_HANDLER_ENABLED},
    {"flap_detection_enabled", MODATTR_FLAP_DETECTION_ENABLED},
    {"failure_prediction_enabled", MODATTR_FAILURE_PREDICTION_ENABLED},
    {"performance_data_enabled", MODATTR_PERFORMANCE_DATA_ENABLED},
    {"obsessive_handler_enabled", MODATTR_OBSESSIVE_HANDLER_ENABLED},
    {"event_handler_command", MODATTR_EVENT_HANDLER_COMMAND},
    {"check_command", MODATTR_CHECK_COMMAND},
    {"normal_check_interval", MODATTR_NORMAL_CHECK_INTERVAL},
    {"retry_check_interval", MODATTR_RETRY_CHECK_INTERVAL},
    {"max_check_attempts", MODATTR_MAX_CHECK_ATTEMPTS},
    {"freshness_checks_enabled", MODATTR_FRESHNESS_CHECKS_ENABLED},
    {"check_timeperiod", MODATTR_CHECK_TIMEPERIOD},
    {"custom_variable", MODATTR_CUSTOM_VARIABLE},
    {"notification_timeperiod", MODATTR_NOTIFICATION_TIMEPERIOD}};
}  // namespace

int32_t AttributeListColumn::getValue(void *row, contact * /*unused*/) {
    char *p = reinterpret_cast<char *>(shiftPointer(row));
    if (p == nullptr) {
        return 0;
    }
    auto ptr = reinterpret_cast<int *>(p + _offset);
    return *reinterpret_cast<int32_t *>(ptr);
}

void AttributeListColumn::output(void *row, RowRenderer &r,
                                 contact * /* auth_user */) {
    unsigned long mask = static_cast<unsigned long>(getValue(row, nullptr));
    ListRenderer l(r);
    for (const auto &entry : known_attributes) {
        if ((mask & entry.second) != 0u) {
            l.output(entry.first);
        }
    }
}

string AttributeListColumn::valueAsString(void *row,
                                          contact * /* auth_user */) {
    return to_string(static_cast<unsigned long>(getValue(row, nullptr)));
}

unique_ptr<Filter> AttributeListColumn::createFilter(RelationalOperator relOp,
                                                     const string &value) {
    return make_unique<IntFilter>(this, relOp, refValueFor(value, logger()));
}

// static
string AttributeListColumn::refValueFor(const string &value, Logger *logger) {
    if (isdigit(value[0]) != 0) {
        return value;
    }

    vector<char> value_vec(value.begin(), value.end());
    value_vec.push_back('\0');
    char *scan = &value_vec[0];

    unsigned long ref_value = 0;
    for (const char *t; (t = next_token(&scan, ',')) != nullptr;) {
        auto it = known_attributes.find(t);
        if (it == known_attributes.end()) {
            Informational(logger) << "Ignoring invalid value '" << t
                                  << "' for attribute list";
            continue;
        }
        ref_value |= it->second;
    }
    return to_string(ref_value);
}
