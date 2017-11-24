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

#include "TimeAggregator.h"
#include <cmath>
#include "Renderer.h"
#include "Row.h"
#include "TimeColumn.h"
#include "contact_fwd.h"

void TimeAggregator::consume(Row row, const contact * /*auth_user*/,
                             std::chrono::seconds timezone_offset) {
    auto value = static_cast<double>(std::chrono::system_clock::to_time_t(
        _column->getValue(row, timezone_offset)));
    _count++;
    switch (_operation) {
        case StatsOperation::sum:
            _aggr += value;
            break;

        case StatsOperation::min:
            if (_count == 1 || value < _aggr) {
                _aggr = value;
            }
            break;

        case StatsOperation::max:
            if (_count == 1 || value > _aggr) {
                _aggr = value;
            }
            break;

        case StatsOperation::avg:
            _aggr += value;
            break;

        case StatsOperation::std:
            _aggr += value;
            _sumq += value * value;
            break;

        case StatsOperation::suminv:
            _aggr += 1.0 / value;
            break;

        case StatsOperation::avginv:
            _aggr += 1.0 / value;
            break;
    }
}

void TimeAggregator::output(RowRenderer &r) const {
    switch (_operation) {
        case StatsOperation::sum:
            r.output(_aggr);
            break;

        case StatsOperation::min:
            r.output(_aggr);
            break;

        case StatsOperation::max:
            r.output(_aggr);
            break;

        case StatsOperation::avg:
            r.output(_aggr / _count);
            break;

        case StatsOperation::std: {
            auto mean = _aggr / _count;
            r.output(sqrt(_sumq / _count - mean * mean));
            break;
        }

        case StatsOperation::suminv:
            r.output(_aggr);
            break;

        case StatsOperation::avginv:
            r.output(_aggr / _count);
            break;
    }
}
