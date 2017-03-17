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

#ifndef HostListStateColumn_h
#define HostListStateColumn_h

#include "config.h"  // IWYU pragma: keep
#include <cstdint>
#include <string>
#include "IntColumn.h"
#include "ServiceListStateColumn.h"
#include "contact_fwd.h"

#ifdef CMC
#include <unordered_set>
class Host;
#else
#include "nagios.h"
#endif

class HostListStateColumn : public IntColumn {
public:
    // TODO(sp) Remove the magic arithmetic
    enum class Type {
        num_svc = static_cast<int>(ServiceListStateColumn::Type::num),
        num_svc_pending =
            static_cast<int>(ServiceListStateColumn::Type::num_pending),
        num_svc_ok = static_cast<int>(ServiceListStateColumn::Type::num_ok),
        num_svc_warn = static_cast<int>(ServiceListStateColumn::Type::num_warn),
        num_svc_crit = static_cast<int>(ServiceListStateColumn::Type::num_crit),
        num_svc_unknown =
            static_cast<int>(ServiceListStateColumn::Type::num_unknown),
        worst_svc_state =
            static_cast<int>(ServiceListStateColumn::Type::worst_state),
        num_svc_hard_ok =
            static_cast<int>(ServiceListStateColumn::Type::num_hard_ok),
        num_svc_hard_warn =
            static_cast<int>(ServiceListStateColumn::Type::num_hard_warn),
        num_svc_hard_crit =
            static_cast<int>(ServiceListStateColumn::Type::num_hard_crit),
        num_svc_hard_unknown =
            static_cast<int>(ServiceListStateColumn::Type::num_hard_unknown),
        worst_svc_hard_state =
            static_cast<int>(ServiceListStateColumn::Type::worst_hard_state),
        num_hst_up = 10,
        num_hst_down = 11,
        num_hst_unreach = 12,
        num_hst_pending = 13,
        num_hst = -11,
        worst_hst_state = -12,
    };

    HostListStateColumn(const std::string &name, const std::string &description,
                        Type logictype, int offset, int indirect_offset,
                        int extra_offset, int extra_extra_offset)
        : IntColumn(name, description, indirect_offset, extra_offset,
                    extra_extra_offset)
        , _offset(offset)
        , _logictype(logictype) {}
    int32_t getValue(void *row, contact *auth_user) override;
#ifdef CMC
    std::unordered_set<Host *> *getMembers(void *data);
#else
    hostsmember *getMembers(void *data);
#endif

private:
    const int _offset;
    const Type _logictype;
};

#endif  // HostListStateColumn_h
