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

#ifndef SectionServices_h
#define SectionServices_h

#include "Section.h"

#ifndef STRICT
#define STRICT
#endif  // STRICT

#ifdef STRICT
#define DECLARE_HANDLE(name) \
    struct name##__ {        \
        int unused;          \
    };                       \
    typedef struct name##__ *name
#else
#define DECLARE_HANDLE(name) typedef HANDLE name
#endif

#if !defined(_WINSVC_) && !defined(_SC_HANDLE_DEFINED_)
#define _SC_HANDLE_DEFINED_
DECLARE_HANDLE(SC_HANDLE);
#endif  // _WINSVC_ && _SC_HANDLE_DEFINED_

typedef const wchar_t *LPCWSTR;

class SectionServices : public Section {
public:
    SectionServices(const Environment &env, Logger *logger,
                    const WinApiAdaptor &winapi);

protected:
    virtual bool produceOutputInner(
        std::ostream &out, const std::optional<std::string> &) override;

private:
    const char *serviceStartType(SC_HANDLE scm, LPCWSTR service_name);
};

#endif  // SectionServices_h
