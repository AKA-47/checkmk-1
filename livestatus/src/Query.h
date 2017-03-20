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

#ifndef Query_h
#define Query_h

// IWYU pragma: no_include <bits/shared_ptr.h>
#include "config.h"  // IWYU pragma: keep
#include <cstdint>
#include <ctime>
#include <list>
#include <map>
#include <memory>
#include <string>
#include <unordered_set>
#include <vector>
#include "AndingFilter.h"
#include "Renderer.h"
#include "RendererBrokenCSV.h"
#include "StatsColumn.h"
#include "VariadicFilter.h"
#include "contact_fwd.h"
#include "data_encoding.h"
#include "opids.h"
class Aggregator;
class Column;
class Filter;
class Logger;
class OutputBuffer;
class Table;

class Query {
public:
    Query(const std::list<std::string> &lines, Table *, Encoding data_encoding,
          OutputBuffer &output);

    bool process();

    bool processDataset(void *);

    bool timelimitReached();
    void invalidRequest(const std::string &message);

    contact *authUser() { return _auth_user; }
    int timezoneOffset() { return _timezone_offset; }

    const std::string *findValueForIndexing(const std::string &column_name);
    void findIntLimits(const std::string &column_name, int *lower, int *upper);
    void optimizeBitmask(const std::string &column_name, uint32_t *bitmask);
    AndingFilter *filter() { return &_filter; }
    const std::unordered_set<std::shared_ptr<Column>> &allColumns() {
        return _all_columns;
    }

private:
    const Encoding _data_encoding;
    OutputBuffer &_output;
    QueryRenderer *_renderer_query;
    Table *_table;
    bool _keepalive;
    AndingFilter _filter;
    contact *_auth_user;
    AndingFilter _wait_condition;
    unsigned _wait_timeout;
    struct trigger *_wait_trigger;
    void *_wait_object;
    CSVSeparators _separators;
    bool _show_column_headers;
    OutputFormat _output_format;
    int _limit;
    int _time_limit;
    time_t _time_limit_timeout;
    unsigned _current_line;
    int _timezone_offset;
    Logger *const _logger;
    std::vector<std::shared_ptr<Column>> _columns;
    std::vector<std::unique_ptr<StatsColumn>> _stats_columns;
    std::map<std::vector<std::string>, std::vector<std::unique_ptr<Aggregator>>>
        _stats_groups;
    std::unordered_set<std::shared_ptr<Column>> _all_columns;

    // invalidHeader can be called during header parsing
    void invalidHeader(const std::string &message);

    void *findTimerangeFilter(const char *columnname, time_t *, time_t *);

    bool doStats();
    void doWait();
    // TODO(sp) The column parameter should actually be a const reference, but
    // Column::createFilter is not const-correct yet...
    std::unique_ptr<Filter> createFilter(Column &column,
                                         RelationalOperator relOp,
                                         const std::string &value);
    void parseFilterLine(char *line, VariadicFilter &filter);
    void parseStatsLine(char *line);
    void parseStatsGroupLine(char *line);
    void parseAndOrLine(char *line, LogicalOperator andor,
                        VariadicFilter &filter, const std::string &header);
    void parseNegateLine(char *line, VariadicFilter &filter,
                         const std::string &header);
    void parseStatsAndOrLine(char *line, LogicalOperator andor);
    void parseStatsNegateLine(char *line);
    void parseColumnsLine(char *line);
    void parseColumnHeadersLine(char *line);
    void parseLimitLine(char *line);
    void parseTimelimitLine(char *line);
    void parseSeparatorsLine(char *line);
    void parseOutputFormatLine(char *line);
    void parseKeepAliveLine(char *line);
    void parseResponseHeaderLine(char *line);
    void parseAuthUserHeader(char *line);
    void parseWaitTimeoutLine(char *line);
    void parseWaitTriggerLine(char *line);
    void parseWaitObjectLine(char *line);
    void parseLocaltimeLine(char *line);
    void start(QueryRenderer &q);
    void finish(QueryRenderer &q);
    const std::vector<std::unique_ptr<Aggregator>> &getAggregatorsFor(
        const std::vector<std::string> &groupspec);
};

#endif  // Query_h
