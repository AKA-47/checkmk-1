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
// ails.  You should have  received  a copy of the  GNU  General Public
// License along with GNU Make; see the file  COPYING.  If  not,  write
// to the Free Software Foundation, Inc., 51 Franklin St,  Fifth Floor,
// Boston, MA 02110-1301 USA.

import $ from "jquery";
import "select2";
import Tagify from "@yaireo/tagify";

import * as utils from "utils";

export function enable_dynamic_form_elements(container=null) {
    enable_select2_dropdowns(container);
    enable_label_input_fields(container);
}

// html.dropdown() adds the .select2-enable class for all dropdowns
// that should use the select2 powered dropdowns
function enable_select2_dropdowns(container) {
    let elements;
    if (container)
        elements = $(container).find(".select2-enable:visible");
    else
        elements = $(".select2-enable:visible");

    elements.select2({
        dropdownAutoWidth : true,
        minimumResultsForSearch: 5
    });
}

function enable_label_input_fields(container) {
    if (!container)
        container = document;

    let elements = container.querySelectorAll("input.labels");
    elements.forEach(element => {
        new Tagify(element, {
            pattern: /^[^:]+:[^:]+$/,
        });
    });
}

// Handle Enter key in textfields
export function textinput_enter_submit(e, submit) {
    if (!e)
        e = window.event;

    var keyCode = e.which || e.keyCode;
    if (keyCode == 13) {
        if (submit) {
            var button = document.getElementById(submit);
            if (button)
                button.click();
        }
        return utils.prevent_default_events(e);
    }
}

