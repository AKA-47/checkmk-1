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

// IWYU pragma: no_include <experimental/bits/fs_ops.h>
// IWYU pragma: no_include <experimental/fs_ops.h>
#include "pnp4nagios.h"
#include <cstddef>
#include <system_error>
#include "MonitoringCore.h"

#ifndef CMC
#include "FileSystem.h"
#endif

using std::string;

namespace {

// TODO(sp): Move this to some kind of C++ string utility file.
string replace_all(const string& str, const string& chars, char replacement) {
    string result(str);
    size_t i = 0;
    while ((i = result.find_first_of(chars, i)) != string::npos) {
        result[i++] = replacement;
    }
    return result;
}
}  // namespace

string pnp_cleanup(const string& name) {
    return replace_all(name, R"( /\:)", '_');
}

#ifndef CMC
// TODO(sp) Merge this with Perfdatabase::getPNPXMLPath
int pnpgraph_present(MonitoringCore* mc, const string& host,
                     const string& service) {
    fs::path pnp_path = mc->pnpPath();
    if (pnp_path.empty()) {
        return -1;
    }
    fs::path path =
        pnp_path / pnp_cleanup(host) / (pnp_cleanup(service) + ".xml");
    std::error_code ec;
    fs::status(path, ec);
    return ec ? 0 : 1;
}
#endif

#ifdef CMC
// TODO(sp) Merge this with Perfdatabase::getPNPRRDPath
fs::path rrd_path(MonitoringCore* mc, const string& host, const string& service,
                  const string& varname) {
    fs::path pnp_path = mc->pnpPath();
    if (pnp_path.empty()) {
        return "";
    }
    fs::path path =
        pnp_path / pnp_cleanup(host) /
        (pnp_cleanup(service) + "_" + pnp_cleanup(varname) + ".rrd");
    std::error_code ec;
    fs::status(path, ec);
    return ec ? "" : path;
}
#endif
