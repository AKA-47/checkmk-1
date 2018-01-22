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

#include "CustomVarsDictFilter.h"
#include <strings.h>
#include <tuple>
#include <unordered_map>
#include <utility>
#include "CustomVarsDictColumn.h"
#include "Filter.h"
#include "Row.h"
#include "StringUtils.h"

CustomVarsDictFilter::CustomVarsDictFilter(const CustomVarsDictColumn &column,
                                           RelationalOperator relOp,
                                           const std::string &value)
    : _column(column), _relOp(relOp), _value(value) {
    // Filter for custom_variables:
    //    Filter: custom_variables = PATH /hirni.mk
    // The variable name is part of the value and separated with spaces
    std::tie(_ref_varname, _ref_string) = mk::nextField(value);
    _ref_string = mk::lstrip(_ref_string);

    // Prepare regular expression
    switch (_relOp) {
        case RelationalOperator::matches:
        case RelationalOperator::doesnt_match:
        case RelationalOperator::matches_icase:
        case RelationalOperator::doesnt_match_icase:
            _regex.assign(_ref_string,
                          (_relOp == RelationalOperator::matches_icase ||
                           _relOp == RelationalOperator::doesnt_match_icase)
                              ? RegExp::Case::ignore
                              : RegExp::Case::respect);
            break;
        case RelationalOperator::equal:
        case RelationalOperator::not_equal:
        case RelationalOperator::equal_icase:
        case RelationalOperator::not_equal_icase:
        case RelationalOperator::less:
        case RelationalOperator::greater_or_equal:
        case RelationalOperator::greater:
        case RelationalOperator::less_or_equal:
            break;
    }
}

bool CustomVarsDictFilter::accepts(
    Row row, const contact * /* auth_user */,
    std::chrono::seconds /* timezone_offset */) const {
    auto cvm = _column.getValue(row);
    auto it = cvm.find(_ref_varname);
    auto act_string = it == cvm.end() ? "" : it->second;
    switch (_relOp) {
        case RelationalOperator::equal:
            return act_string == _ref_string;
        case RelationalOperator::not_equal:
            return act_string != _ref_string;
        case RelationalOperator::matches:
        case RelationalOperator::matches_icase:
            return _regex.search(act_string);
        case RelationalOperator::doesnt_match:
        case RelationalOperator::doesnt_match_icase:
            return !_regex.search(act_string);
        case RelationalOperator::equal_icase:
            return strcasecmp(_ref_string.c_str(), act_string.c_str()) == 0;
        case RelationalOperator::not_equal_icase:
            return strcasecmp(_ref_string.c_str(), act_string.c_str()) != 0;
        case RelationalOperator::less:
            return act_string < _ref_string;
        case RelationalOperator::greater_or_equal:
            return act_string >= _ref_string;
        case RelationalOperator::greater:
            return act_string > _ref_string;
        case RelationalOperator::less_or_equal:
            return act_string <= _ref_string;
    }
    return false;  // unreachable
}

std::unique_ptr<Filter> CustomVarsDictFilter::copy() const {
    return std::make_unique<CustomVarsDictFilter>(*this);
}

std::unique_ptr<Filter> CustomVarsDictFilter::negate() const {
    return std::make_unique<CustomVarsDictFilter>(
        _column, negateRelationalOperator(_relOp), _value);
}

std::string CustomVarsDictFilter::columnName() const { return _column.name(); }
