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

#ifndef ServiceListColumn_h
#define ServiceListColumn_h

#include "config.h"  // IWYU pragma: keep
#include <memory>
#include <string>
#include "Column.h"
#include "opids.h"
class Filter;
class RowRenderer;

#ifdef CMC
#include <unordered_set>
#include "cmc.h"
class Service;
#else
#include "nagios.h"
#endif

class ServiceListColumn : public Column {
public:
    ServiceListColumn(const std::string &name, const std::string &description,
                      bool hostname_required, bool show_host, int info_depth,
                      int offset, int indirect_offset, int extra_offset,
                      int extra_extra_offset)
        : Column(name, description, indirect_offset, extra_offset,
                 extra_extra_offset)
        , _hostname_required(hostname_required)
        , _offset(offset)
        , _show_host(show_host)
        , _info_depth(info_depth) {}
    ColumnType type() override { return ColumnType::list; };
    void output(void *row, RowRenderer &r, contact *auth_user) override;
    std::unique_ptr<Filter> createFilter(RelationalOperator relOp,
                                         const std::string &value) override;
#ifdef CMC
    std::unordered_set<Service *> *getMembers(void *data);
#else
    servicesmember *getMembers(void *data);
#endif

private:
    bool _hostname_required;
    int _offset;
    bool _show_host;
    int _info_depth;

#ifndef CMC
    int inCustomTimeperiod(service *svc, const char *varname);
#endif
};

#endif  // ServiceListColumn_h
