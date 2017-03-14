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

#ifndef Store_h
#define Store_h

#include "config.h"  // IWYU pragma: keep
#include <list>
#include <map>
#include <string>
#include "LogCache.h"
#include "TableColumns.h"
#include "TableCommands.h"
#include "TableComments.h"
#include "TableContactGroups.h"
#include "TableContacts.h"
#include "TableDowntimes.h"
#include "TableEventConsoleEvents.h"
#include "TableEventConsoleHistory.h"
#include "TableEventConsoleReplication.h"
#include "TableEventConsoleRules.h"
#include "TableEventConsoleStatus.h"
#include "TableHostGroups.h"
#include "TableHosts.h"
#include "TableHostsByGroup.h"
#include "TableLog.h"
#include "TableServiceGroups.h"
#include "TableServices.h"
#include "TableServicesByGroup.h"
#include "TableServicesByHostGroup.h"
#include "TableStateHistory.h"
#include "TableStatus.h"
#include "TableTimeperiods.h"
class InputBuffer;
class Logger;
class MonitoringCore;
class OutputBuffer;
class Table;

#ifdef CMC
#include <cstdint>
#include "TableCachedStatehist.h"
class Config;
class Core;
class Object;
#else
#include <mutex>
#include "CommandsHolderNagios.h"
#include "DowntimesOrComments.h"
#include "nagios.h"
#endif

class Store {
public:
#ifdef CMC
    Store(MonitoringCore *mc, Core *core);
    LogCache *logCache() { return &_log_cache; };
    bool answerRequest(InputBuffer *, OutputBuffer *);
    bool answerGetRequest(const std::list<std::string> &lines,
                          OutputBuffer &output, const std::string &tablename);
    void answerCommandRequest(const char *command, Logger *logger);
    void setMaxCachedMessages(unsigned long m);
    void switchStatehistTable();
    void buildStatehistCache();
    void flushStatehistCache();
    void tryFinishStatehistCache();
    bool addObjectHistcache(Object *);
    void addAlertToStatehistCache(Object *, int state, const char *output);
    void addDowntimeToStatehistCache(Object *, bool started);
    void addFlappingToStatehistCache(Object *, bool started);
    Logger *logger() const { return _logger; }
#else
    explicit Store(MonitoringCore *mc);
    bool answerRequest(InputBuffer &input, OutputBuffer &output);

    void registerDowntime(nebstruct_downtime_data *);
    void registerComment(nebstruct_comment_data *);
#endif

private:
#ifdef CMC
    Core *_core;
#else
    MonitoringCore *_mc;
#endif
    Logger *const _logger;
#ifndef CMC
    CommandsHolderNagios _commands_holder;
    DowntimesOrComments _downtimes;
    DowntimesOrComments _comments;
#endif
    LogCache _log_cache;

#ifdef CMC
    TableCachedStatehist _table_cached_statehist;
#endif
    TableColumns _table_columns;
    TableCommands _table_commands;
    TableComments _table_comments;
    TableContactGroups _table_contactgroups;
    TableContacts _table_contacts;
    TableDowntimes _table_downtimes;
    TableEventConsoleEvents _table_eventconsoleevents;
    TableEventConsoleHistory _table_eventconsolehistory;
    TableEventConsoleReplication _table_eventconsolereplication;
    TableEventConsoleRules _table_eventconsolerules;
    TableEventConsoleStatus _table_eventconsolestatus;
    TableHostGroups _table_hostgroups;
    TableHosts _table_hosts;
    TableHostsByGroup _table_hostsbygroup;
    TableLog _table_log;
    TableServiceGroups _table_servicegroups;
    TableServices _table_services;
    TableServicesByGroup _table_servicesbygroup;
    TableServicesByHostGroup _table_servicesbyhostgroup;
    TableStateHistory _table_statehistory;
    TableStatus _table_status;
    TableTimeperiods _table_timeperiods;

    std::map<std::string, Table *> _tables;

#ifndef CMC
    std::mutex _command_mutex;
#endif

    void addTable(Table *table);
    Table *findTable(const std::string &name);
#ifdef CMC
    Config *config() const;
    uint32_t horizon() const;
#else
    void logRequest(const std::string &line,
                    const std::list<std::string> &lines);
    bool answerGetRequest(const std::list<std::string> &lines,
                          OutputBuffer &output, const std::string &tablename);
    void answerCommandRequest(const char *);
    bool handleCommand(const std::string &command);
#endif
};

#endif  // Store_h
