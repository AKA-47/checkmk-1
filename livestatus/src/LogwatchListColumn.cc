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

#include "LogwatchListColumn.h"
#include <ostream>
#include "FileSystem.h"
#include "Logger.h"
#include "Renderer.h"
#include "pnp4nagios.h"

#ifdef CMC
#include "Host.h"
#endif

using std::string;

void LogwatchListColumn::output(void *row, RowRenderer &r,
                                contact * /* auth_user */) {
    ListRenderer l(r);
    if (_logwatch_path.empty()) {
        return;
    }

#ifdef CMC
    auto hst = rowData<Host>(row);
    if (hst == nullptr) {
        return;
    }
    string host_name = hst->name();
#else
    auto hst = rowData<host>(row);
    if (hst == nullptr) {
        return;
    }
    string host_name = hst->name;
#endif

    auto dir = _logwatch_path + pnp_cleanup(host_name);
    try {
        if (fs::exists(dir)) {
            for (const auto &entry : fs::directory_iterator(dir)) {
                l.output(entry.path().filename().string());
            }
        }
    } catch (const fs::filesystem_error &e) {
        Warning(logger()) << name() << ": " << e.what();
    }
}
