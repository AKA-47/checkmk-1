#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.
"""
This module handles tree structures for HW/SW inventory system and
structured monitoring data of Check_MK.
"""

import io
import gzip
import re
from pathlib import Path
import pprint
from typing import (
    Dict,
    List,
    Optional,
    Any,
    Union,
    Tuple,
    Set,
    Callable,
    NamedTuple,
    Literal,
    Counter as TCounter,
    Sequence,
)
from collections import Counter

from cmk.utils import store

from cmk.utils.type_defs import HostName

from cmk.utils.exceptions import MKGeneralException

# TODO Cleanup path in utils, base, gui, find ONE place (type defs or similar)
# TODO
# - is_empty -> __bool__
# - is_equal -> __eq__/__ne__
# - merge_with -> __add__
# - count_entries -> __len__?
# TODO remove has_edge

SDRawPath = str
SDRawTree = Dict

SDEdge = str
SDPath = List[SDEdge]

SDKey = str
SDKeys = List[SDKey]
# TODO be more specific (None, str, float, int, DeltaValue:Tuple of previous)
SDValue = Any  # needs only to support __eq__
SDAttributes = Dict[SDKey, SDValue]
# TODO SDTAble and LegacyTable are the same for now, but SDTable will change in the future
SDTable = List[SDAttributes]
LegacyTable = List[SDAttributes]
SDNodePath = Tuple[SDEdge, ...]
SDNodes = Dict[SDEdge, "StructuredDataNode"]

SDEncodeAs = Callable
SDDeltaCounter = TCounter[Literal["new", "changed", "removed"]]


class SDDeltaResult(NamedTuple):
    counter: SDDeltaCounter
    delta: "StructuredDataNode"


class NDeltaResult(NamedTuple):
    counter: SDDeltaCounter
    delta: "Table"


class TDeltaResult(NamedTuple):
    counter: SDDeltaCounter
    delta: SDTable


class ADeltaResult(NamedTuple):
    counter: SDDeltaCounter
    delta: "Attributes"


class DDeltaResult(NamedTuple):
    counter: SDDeltaCounter
    delta: SDAttributes


SDFilterFunc = Callable[[SDKey], bool]


class SDFilter(NamedTuple):
    path: SDPath
    filter_nodes: SDFilterFunc
    filter_attributes: SDFilterFunc
    filter_columns: SDFilterFunc


#   .--IO------------------------------------------------------------------.
#   |                              ___ ___                                 |
#   |                             |_ _/ _ \                                |
#   |                              | | | | |                               |
#   |                              | | |_| |                               |
#   |                             |___\___/                                |
#   |                                                                      |
#   '----------------------------------------------------------------------'


def save_tree_to(
    tree: "StructuredDataNode",
    path: str,
    filename: str,
    pretty: bool = False,
) -> None:
    filepath = "%s/%s" % (path, filename)
    output = tree.serialize()
    store.save_object_to_file(filepath, output, pretty=pretty)

    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as f:
        f.write((repr(output) + "\n").encode("utf-8"))
    store.save_bytes_to_file(filepath + ".gz", buf.getvalue())

    # Inform Livestatus about the latest inventory update
    store.save_text_to_file("%s/.last" % path, u"")


class StructuredDataStore:
    @staticmethod
    def load_file(file_path: Path) -> "StructuredDataNode":
        if raw_tree := store.load_object_from_file(file_path, default=None):
            return StructuredDataNode.deserialize(raw_tree)
        return StructuredDataNode()

    def __init__(self, path: Path) -> None:
        self._path = path

    def _host_file(self, host_name: HostName) -> Path:
        return self._path / str(host_name)

    def load(self, host_name: HostName) -> "StructuredDataNode":
        return self.load_file(self._host_file(host_name))


#.
#   .--filters-------------------------------------------------------------.
#   |                       __ _ _ _                                       |
#   |                      / _(_) | |_ ___ _ __ ___                        |
#   |                     | |_| | | __/ _ \ '__/ __|                       |
#   |                     |  _| | | ||  __/ |  \__ \                       |
#   |                     |_| |_|_|\__\___|_|  |___/                       |
#   |                                                                      |
#   '----------------------------------------------------------------------'

_use_all = lambda key: True
_use_nothing = lambda key: False


def _make_choices_filter(choices: Sequence[Union[str, int]]) -> SDFilterFunc:
    return lambda key: key in choices


def make_filter(entry: Union[Tuple[SDPath, Optional[SDKeys]], Dict]) -> SDFilter:
    if isinstance(entry, tuple):
        path, keys = entry
        return SDFilter(
            path=path,
            filter_nodes=_use_all,
            filter_attributes=_use_all,
            filter_columns=_use_all,
        ) if keys is None else SDFilter(
            path=path,
            filter_nodes=_use_nothing,
            filter_attributes=_make_choices_filter(keys) if keys else _use_all,
            filter_columns=_make_choices_filter(keys) if keys else _use_all,
        )

    return SDFilter(
        path=parse_visible_raw_path(entry["visible_raw_path"]),
        filter_attributes=_make_filter_from_choice(entry.get("attributes")),
        filter_columns=_make_filter_from_choice(entry.get("columns")),
        filter_nodes=_make_filter_from_choice(entry.get("nodes")),
    )


def _make_filter_from_choice(choice: Union[Tuple[str, List[str]], str, None]) -> SDFilterFunc:
    # choice is of the form:
    #   - ('choices', ['some', 'keys'])
    #   - 'nothing'
    #   - None means _use_all
    if isinstance(choice, tuple):
        return _make_choices_filter(choice[-1])
    if choice == "nothing":
        return _use_nothing
    return _use_all


#.
#   .--Structured DataNode-------------------------------------------------.
#   |         ____  _                   _                      _           |
#   |        / ___|| |_ _ __ _   _  ___| |_ _   _ _ __ ___  __| |          |
#   |        \___ \| __| '__| | | |/ __| __| | | | '__/ _ \/ _` |          |
#   |         ___) | |_| |  | |_| | (__| |_| |_| | | |  __/ (_| |          |
#   |        |____/ \__|_|   \__,_|\___|\__|\__,_|_|  \___|\__,_|          |
#   |                                                                      |
#   |             ____        _        _   _           _                   |
#   |            |  _ \  __ _| |_ __ _| \ | | ___   __| | ___              |
#   |            | | | |/ _` | __/ _` |  \| |/ _ \ / _` |/ _ \             |
#   |            | |_| | (_| | || (_| | |\  | (_) | (_| |  __/             |
#   |            |____/ \__,_|\__\__,_|_| \_|\___/ \__,_|\___|             |
#   |                                                                      |
#   '----------------------------------------------------------------------'


class StructuredDataNode:
    def __init__(self) -> None:
        self.path: SDNodePath = tuple()
        self.attributes = Attributes()
        self.table = Table()
        self._nodes: SDNodes = {}

        self._legacy_table: LegacyTable = []

    def set_path(self, path: SDNodePath) -> None:
        self.path = path
        self.attributes.set_path(path)
        self.table.set_path(path)

    def is_empty(self) -> bool:
        if not (self.attributes.is_empty() and self.table.is_empty()):
            return False

        for node in self._nodes.values():
            if not node.is_empty():
                return False
        return True

    def is_equal(self, other: object, edges: Optional[SDPath] = None) -> bool:
        if not isinstance(other, StructuredDataNode):
            raise TypeError("Cannot compare %s with %s" % (type(self), type(other)))

        if not (self.attributes.is_equal(other.attributes) and self.table.is_equal(other.table)):
            return False

        compared_keys = _compare_dict_keys(old_dict=other._nodes, new_dict=self._nodes)
        if compared_keys.only_old or compared_keys.only_new:
            return False

        for key in compared_keys.both:
            if not self._nodes[key].is_equal(other._nodes[key]):
                return False
        return True

    def count_entries(self) -> int:
        return sum([
            self.attributes.count_entries(),
            self.table.count_entries(),
        ] + [node.count_entries() for node in self._nodes.values()])

    def merge_with(self, other: object) -> None:
        if not isinstance(other, StructuredDataNode):
            raise TypeError("Cannot compare %s with %s" % (type(self), type(other)))

        self.attributes.merge_with(other.attributes)
        self.table.merge_with(other.table)

        compared_keys = _compare_dict_keys(old_dict=other._nodes, new_dict=self._nodes)

        for key in compared_keys.both:
            self._nodes[key].merge_with(other._nodes[key])

        for key in compared_keys.only_old:
            self.add_node(key, other._nodes[key])

    def copy(self) -> "StructuredDataNode":
        new_node = StructuredDataNode()

        new_node.add_attributes(self.attributes.data)
        new_node.add_table(self.table.data)

        for edge, node in self._nodes.items():
            new_node.add_node(edge, node.copy())
        return new_node

    #   ---node methods---------------------------------------------------------

    def setdefault_node(self, path: SDPath) -> "StructuredDataNode":
        if not path:
            return self
        edge = path[0]
        node = self._nodes.setdefault(edge, StructuredDataNode())
        node.set_path(self.path + (edge,))
        return node.setdefault_node(path[1:])

    def add_node(self, edge: SDEdge, node: "StructuredDataNode") -> "StructuredDataNode":
        the_node = self._nodes.setdefault(edge, StructuredDataNode())
        the_node.set_path(self.path + (edge,))
        the_node.merge_with(node)
        return the_node

    def add_attributes(self, attributes: SDAttributes) -> None:
        self.attributes.add_attributes(attributes)

    def add_table(self, table: SDTable) -> None:
        self.table.add_table(table)

    def has_edge(self, edge: SDEdge) -> bool:
        return bool(self._nodes.get(edge))

    def get_node(self, path: SDPath) -> Optional["StructuredDataNode"]:
        return self._get_node(path)

    def get_table(self, path: SDPath) -> Optional["Table"]:
        node = self._get_node(path)
        return None if node is None else node.table

    def get_attributes(self, path: SDPath) -> Optional["Attributes"]:
        node = self._get_node(path)
        return None if node is None else node.attributes

    def _get_node(self, path: SDPath) -> Optional["StructuredDataNode"]:
        if not path:
            return self
        node = self._nodes.get(path[0])
        return None if node is None else node._get_node(path[1:])

    #   ---representation-------------------------------------------------------

    def __repr__(self) -> str:
        return "%s(%s)" % (self.__class__.__name__, pprint.pformat(self.serialize()))

    #   ---building tree from (legacy) plugins----------------------------------

    def get_dict(self, tree_path: Optional[SDRawPath]) -> SDAttributes:
        return self.setdefault_node(_parse_tree_path(tree_path)).attributes.data

    def get_list(self, tree_path: Optional[SDRawPath]) -> SDTable:
        return self.setdefault_node(_parse_tree_path(tree_path))._legacy_table

    #   ---de/serializing-------------------------------------------------------

    @classmethod
    def deserialize(cls, raw_tree: SDRawTree) -> "StructuredDataNode":
        node = cls()
        raw_attributes: SDAttributes = {}

        for key, value in raw_tree.items():
            if isinstance(value, dict):
                if not value:
                    continue
                node.add_node(key, cls.deserialize(value))

            elif isinstance(value, list):
                if not value:
                    continue

                if node._is_table(value):
                    node.setdefault_node([key]).add_table(Table.deserialize(value))
                else:
                    indexed_node = node.setdefault_node([key])
                    for idx, entry in enumerate(value):
                        indexed_node.add_node(str(idx), cls.deserialize(entry))

            else:
                raw_attributes.setdefault(key, value)

        node.add_attributes(Attributes.deserialize(raw_attributes))
        return node

    @staticmethod
    def _is_table(entries: List) -> bool:
        # Either we get:
        #   [
        #       {"column1": "value 11", "column2": "value 12",...},
        #       {"column1": "value 11", "column2": "value 12",...},
        #       ...
        #   ]
        # Or:
        #   [
        #       {"attr": "attr1", "table": [...], "node": {...}, "idx-node": [...]},
        #       ...
        #   ]
        return all(not isinstance(v, (list, dict)) for row in entries for v in row.values())

    def serialize(self) -> Union[Dict, List]:
        if any(self._is_indexed_node(edge) for edge in self._nodes):
            return [self._nodes[k].serialize() for k in sorted(self._nodes)]

        if not self.table.is_empty():
            return self.table.serialize()

        tree: Dict = {}
        tree.update(self.attributes.serialize())

        for edge, node in self._nodes.items():
            node_raw_tree = node.serialize()
            if isinstance(node_raw_tree, list):
                tree.setdefault(edge, node_raw_tree)
                continue

            tree.setdefault(edge, {}).update(node_raw_tree)
        return tree

    @staticmethod
    def _is_indexed_node(edge: Union[int, SDEdge]) -> bool:
        try:
            int(edge)
        except ValueError:
            return False
        return True

    def normalize_nodes(self):
        """
        After the execution of inventory we have to deal with nested tables, eg.
        at paths like "hardware.memory.arrays:*.devices:" where
        we obtain: 'memory': {'arrays': [{'devices': [...]}, {}, ... ]}.
        In this case we have to convert this
        'list-composed-of-dicts-containing-lists' structure into
        indexed nodes ('arrays') containing real tables ('devices').
        """
        my_table: SDTable = []
        for idx, entry in enumerate(self._legacy_table):
            add_to_my_table = True
            for k, v in entry.items():
                if isinstance(v, list):
                    self.setdefault_node([str(idx), k]).add_table(Table.deserialize(v))
                    add_to_my_table = False

            if add_to_my_table:
                my_table.append(entry)

        self.table.add_table(Table.deserialize(my_table))

        # normalize_nodes is executed after all plugins: clear legacy_table
        # in order to avoid duplicate rows if executed multiple times (should not happen).
        self._legacy_table = []

        for node in self._nodes.values():
            node.normalize_nodes()

    #   ---delta----------------------------------------------------------------

    def compare_with(self, other: object, keep_identical: bool = False) -> SDDeltaResult:
        if not isinstance(other, StructuredDataNode):
            raise TypeError("Cannot compare %s with %s" % (type(self), type(other)))

        counter: SDDeltaCounter = Counter()
        delta_node = StructuredDataNode()

        # Attributes
        delta_attributes_result = self.attributes.compare_with(other.attributes)
        counter.update(delta_attributes_result.counter)
        delta_node.add_attributes(delta_attributes_result.delta.data)

        # Table
        delta_table_result = self.table.compare_with(other.table)
        counter.update(delta_table_result.counter)
        delta_node.add_table(delta_table_result.delta.data)

        # Nodes
        compared_keys = _compare_dict_keys(old_dict=other._nodes, new_dict=self._nodes)

        for key in compared_keys.only_new:
            node = self._nodes[key]
            new_entries = node.count_entries()
            if new_entries:
                counter.update(new=new_entries)
                delta_node.add_node(
                    key,
                    node.get_encoded_node(encode_as=_new_delta_tree_node),
                )

        for key in compared_keys.both:
            node = self._nodes[key]
            other_node = other._nodes[key]

            if node.is_equal(other_node):
                if keep_identical:
                    delta_node.add_node(
                        key,
                        node.get_encoded_node(encode_as=_identical_delta_tree_node),
                    )
                continue

            delta_node_result = node.compare_with(
                other_node,
                keep_identical=keep_identical,
            )

            if (delta_node_result.counter['new'] or delta_node_result.counter['changed'] or
                    delta_node_result.counter['removed']):
                counter.update(delta_node_result.counter)
                delta_node.add_node(key, delta_node_result.delta)

        for key in compared_keys.only_old:
            other_node = other._nodes[key]
            removed_entries = other_node.count_entries()
            if removed_entries:
                counter.update(removed=removed_entries)
                delta_node.add_node(
                    key,
                    other_node.get_encoded_node(encode_as=_removed_delta_tree_node),
                )

        return SDDeltaResult(counter=counter, delta=delta_node)

    def get_encoded_node(self, encode_as: SDEncodeAs) -> "StructuredDataNode":
        delta_node = StructuredDataNode()

        delta_node.add_attributes(self.attributes.get_encoded_attributes(encode_as))
        delta_node.add_table(self.table.get_encoded_table(encode_as))

        for edge, node in self._nodes.items():
            delta_node.add_node(edge, node.get_encoded_node(encode_as))
        return delta_node

    #   ---filtering------------------------------------------------------------

    def get_filtered_node(self, filters: List[SDFilter]) -> "StructuredDataNode":
        filtered = StructuredDataNode()
        for f in filters:
            # First check if node exists
            node = self._get_node(f.path)
            if node is None:
                continue

            filtered_node = filtered.setdefault_node(f.path)

            filtered_node.add_attributes(node.attributes.get_filtered_data(f.filter_attributes))

            filtered_node.add_table(node.table.get_filtered_data(f.filter_columns))

            for edge, sub_node in node._nodes.items():
                # From GUI::permitted_paths: We always get a list of strs.
                if f.filter_nodes(str(edge)):
                    filtered_node.add_node(edge, sub_node)

        return filtered

    #   ---web------------------------------------------------------------------

    def show(self, renderer):
        # TODO
        if not self.attributes.is_empty():
            renderer.show_attributes(self.attributes)

        if not self.table.is_empty():
            renderer.show_table(self.table)

        for edge in sorted(self._nodes):
            renderer.show_node(self._nodes[edge])


#.
#   .--Table---------------------------------------------------------------.
#   |                       _____     _     _                              |
#   |                      |_   _|_ _| |__ | | ___                         |
#   |                        | |/ _` | '_ \| |/ _ \                        |
#   |                        | | (_| | |_) | |  __/                        |
#   |                        |_|\__,_|_.__/|_|\___|                        |
#   |                                                                      |
#   '----------------------------------------------------------------------'


class Table:
    def __init__(self) -> None:
        self.path: SDNodePath = tuple()
        self.data: SDTable = []

    def set_path(self, path: SDNodePath) -> None:
        self.path = path

    def is_empty(self) -> bool:
        return self.data == []

    def is_equal(self, other: object, edges: Optional[SDPath] = None) -> bool:
        if not isinstance(other, Table):
            raise TypeError("Cannot compare %s with %s" % (type(self), type(other)))

        for row in self.data:
            if row not in other.data:
                return False
        for row in other.data:
            if row not in self.data:
                return False
        return True

    def count_entries(self) -> int:
        return sum(map(len, self.data))

    def merge_with(self, other: object) -> None:
        if not isinstance(other, Table):
            raise TypeError("Cannot compare %s with %s" % (type(self), type(other)))

        other_keys = other._get_table_keys()
        my_keys = self._get_table_keys()
        intersect_keys = my_keys.intersection(other_keys)

        # In case there is no intersection, append all other rows without
        # merging with own rows
        if not intersect_keys:
            self.add_table(other.data)
            return

        # Try to match rows of both trees based on the keys that are found in
        # both. Matching rows are updated. Others are appended.
        other_num = {other._prepare_key(entry, intersect_keys): entry for entry in other.data}

        for entry in self.data:
            key = self._prepare_key(entry, intersect_keys)
            if key in other_num:
                entry.update(other_num[key])
                del other_num[key]

        self.add_table(list(other_num.values()))

    def _get_table_keys(self) -> Set[SDKey]:
        return {key for row in self.data for key in row}

    def _prepare_key(self, entry: Dict, keys: Set[SDKey]) -> Tuple[SDKey, ...]:
        return tuple(entry[key] for key in sorted(keys) if key in entry)

    #   ---table methods--------------------------------------------------------

    def add_table(self, table: SDTable) -> None:
        for row in table:
            self.add_row(row)

    def add_row(self, row: SDAttributes) -> None:
        if row:
            self.data.append(row)

    #   ---de/serializing-------------------------------------------------------

    def serialize(self) -> SDTable:
        return self.data

    @classmethod
    def deserialize(cls, raw_table: SDTable) -> "SDTable":
        return raw_table

    #   ---delta----------------------------------------------------------------

    def compare_with(self, other: object, keep_identical: bool = False) -> NDeltaResult:
        if not isinstance(other, Table):
            raise TypeError("Cannot compare %s with %s" % (type(self), type(other)))

        counter: SDDeltaCounter = Counter()
        delta_table = Table()

        remaining_own_rows, remaining_other_rows, identical_rows = self._get_categorized_rows(other)
        new_rows: List = []
        removed_rows: List = []

        if not remaining_other_rows and remaining_own_rows:
            new_rows.extend(remaining_own_rows)

        elif remaining_other_rows and not remaining_own_rows:
            removed_rows.extend(remaining_other_rows)

        elif remaining_other_rows and remaining_own_rows:
            if len(remaining_other_rows) == len(remaining_own_rows):
                delta_rows_result = self._compare_remaining_rows_with_same_length(
                    remaining_own_rows,
                    remaining_other_rows,
                    keep_identical=keep_identical,
                )
                counter.update(delta_rows_result.counter)
                delta_table.add_table(delta_rows_result.delta)
            else:
                new_rows.extend(remaining_own_rows)
                removed_rows.extend(remaining_other_rows)

        delta_table.add_table(
            [{k: _new_delta_tree_node(v) for k, v in row.items()} for row in new_rows])
        delta_table.add_table(
            [{k: _removed_delta_tree_node(v) for k, v in row.items()} for row in removed_rows])

        if keep_identical:
            delta_table.add_table([
                {k: _identical_delta_tree_node(v) for k, v in row.items()} for row in identical_rows
            ])

        counter.update(new=sum(map(len, new_rows)), removed=sum(map(len, removed_rows)))
        return NDeltaResult(counter=counter, delta=delta_table)

    def _get_categorized_rows(self, other: "Table") -> Tuple[SDTable, SDTable, SDTable]:
        identical_rows = []
        remaining_other_rows = []
        remaining_new_rows = []
        for row in other.data:
            if row in self.data:
                if row not in identical_rows:
                    identical_rows.append(row)
            else:
                remaining_other_rows.append(row)
        for row in self.data:
            if row in other.data:
                if row not in identical_rows:
                    identical_rows.append(row)
            else:
                remaining_new_rows.append(row)
        return remaining_new_rows, remaining_other_rows, identical_rows

    def _compare_remaining_rows_with_same_length(
        self,
        own_rows: SDTable,
        other_rows: SDTable,
        keep_identical: bool = False,
    ) -> TDeltaResult:
        # In this case we assume that each entry corresponds to the
        # other one with the same index.
        counter: SDDeltaCounter = Counter()
        compared_rows = []
        for own_row, other_row in zip(own_rows, other_rows):
            delta_dict_result = _compare_dicts(
                old_dict=other_row,
                new_dict=own_row,
                keep_identical=keep_identical,
            )

            counter.update(delta_dict_result.counter)
            if delta_dict_result.delta:
                compared_rows.append(delta_dict_result.delta)
        return TDeltaResult(counter=counter, delta=compared_rows)

    def get_encoded_table(self, encode_as: SDEncodeAs) -> SDTable:
        return [{k: encode_as(v) for k, v in row.items()} for row in self.data]

    #   ---filtering------------------------------------------------------------

    def get_filtered_data(self, filter_func: SDFilterFunc) -> SDTable:
        return [
            filtered_row for row in self.data
            if (filtered_row := _get_filtered_dict(row, filter_func))
        ]

    #   ---web------------------------------------------------------------------

    def show(self, renderer):
        # TODO
        renderer.show_table(self)


#.
#   .--Attributes----------------------------------------------------------.
#   |              _   _   _        _ _           _                        |
#   |             / \ | |_| |_ _ __(_) |__  _   _| |_ ___  ___             |
#   |            / _ \| __| __| '__| | '_ \| | | | __/ _ \/ __|            |
#   |           / ___ \ |_| |_| |  | | |_) | |_| | ||  __/\__ \            |
#   |          /_/   \_\__|\__|_|  |_|_.__/ \__,_|\__\___||___/            |
#   |                                                                      |
#   '----------------------------------------------------------------------'


class Attributes:
    def __init__(self) -> None:
        self.path: SDNodePath = tuple()
        self.data: SDAttributes = {}

    def set_path(self, path: SDNodePath) -> None:
        self.path = path

    def is_empty(self) -> bool:
        return self.data == {}

    def is_equal(self, other: object, edges: Optional[SDPath] = None) -> bool:
        if not isinstance(other, Attributes):
            raise TypeError("Cannot compare %s with %s" % (type(self), type(other)))

        return self.data == other.data

    def count_entries(self) -> int:
        return len(self.data)

    def merge_with(self, other: object) -> None:
        if not isinstance(other, Attributes):
            raise TypeError("Cannot compare %s with %s" % (type(self), type(other)))

        self.data.update(other.data)

    #   ---attributes methods---------------------------------------------------

    def add_attributes(self, attributes: SDAttributes) -> None:
        self.data.update(attributes)

    #   ---de/serializing-------------------------------------------------------

    def serialize(self) -> SDAttributes:
        return self.data

    @classmethod
    def deserialize(cls, raw_attributes: SDAttributes) -> "SDAttributes":
        return raw_attributes

    #   ---delta----------------------------------------------------------------

    def compare_with(self, other: object, keep_identical: bool = False) -> ADeltaResult:
        if not isinstance(other, Attributes):
            raise TypeError("Cannot compare %s with %s" % (type(self), type(other)))

        delta_dict_result = _compare_dicts(
            old_dict=other.data,
            new_dict=self.data,
            keep_identical=keep_identical,
        )

        delta_attributes = Attributes()
        delta_attributes.add_attributes(delta_dict_result.delta)

        return ADeltaResult(
            counter=delta_dict_result.counter,
            delta=delta_attributes,
        )

    def get_encoded_attributes(self, encode_as: SDEncodeAs) -> SDAttributes:
        return {k: encode_as(v) for k, v in self.data.items()}

    #   ---filtering------------------------------------------------------------

    def get_filtered_data(self, filter_func: SDFilterFunc) -> SDAttributes:
        return _get_filtered_dict(self.data, filter_func)

    #   ---web------------------------------------------------------------------

    def show(self, renderer):
        # TODO
        renderer.show_attributes(self)


#.
#   .--helpers-------------------------------------------------------------.
#   |                  _          _                                        |
#   |                 | |__   ___| |_ __   ___ _ __ ___                    |
#   |                 | '_ \ / _ \ | '_ \ / _ \ '__/ __|                   |
#   |                 | | | |  __/ | |_) |  __/ |  \__ \                   |
#   |                 |_| |_|\___|_| .__/ \___|_|  |___/                   |
#   |                              |_|                                     |
#   '----------------------------------------------------------------------'


def _compare_dicts(*, old_dict: Dict, new_dict: Dict, keep_identical: bool) -> DDeltaResult:
    """
    Format of compared entries:
      new:          {k: (None, new_value), ...}
      changed:      {k: (old_value, new_value), ...}
      removed:      {k: (old_value, None), ...}
      identical:    {k: (value, value), ...}
    """
    compared_keys = _compare_dict_keys(old_dict=old_dict, new_dict=new_dict)

    identical: Dict = {}
    changed: Dict = {}
    for k in compared_keys.both:
        new_value = new_dict[k]
        old_value = old_dict[k]
        if new_value == old_value:
            identical.setdefault(k, _identical_delta_tree_node(old_value))
        else:
            changed.setdefault(k, _changed_delta_tree_node(old_value, new_value))

    new = {k: _new_delta_tree_node(new_dict[k]) for k in compared_keys.only_new}
    removed = {k: _removed_delta_tree_node(old_dict[k]) for k in compared_keys.only_old}

    delta_dict: Dict = {}
    delta_dict.update(new)
    delta_dict.update(changed)
    delta_dict.update(removed)
    if keep_identical:
        delta_dict.update(identical)

    return DDeltaResult(
        counter=Counter(new=len(new), changed=len(changed), removed=len(removed)),
        delta=delta_dict,
    )


class ComparedDictKeys(NamedTuple):
    only_old: Set
    both: Set
    only_new: Set


def _compare_dict_keys(*, old_dict: Dict, new_dict: Dict) -> ComparedDictKeys:
    """
    Returns the set relationships of the keys between two dictionaries:
    - relative complement of new_dict in old_dict
    - intersection of both
    - relative complement of old_dict in new_dict
    """
    old_keys, new_keys = set(old_dict), set(new_dict)
    return ComparedDictKeys(
        only_old=old_keys - new_keys,
        both=old_keys.intersection(new_keys),
        only_new=new_keys - old_keys,
    )


def _get_filtered_dict(dict_: Dict, filter_func: SDFilterFunc) -> Dict:
    return {k: v for k, v in dict_.items() if filter_func(k)}


def _new_delta_tree_node(value: SDValue) -> Tuple[None, SDValue]:
    return (None, value)


def _removed_delta_tree_node(value: SDValue) -> Tuple[SDValue, None]:
    return (value, None)


def _changed_delta_tree_node(old_value: SDValue, new_value: SDValue) -> Tuple[SDValue, SDValue]:
    return (old_value, new_value)


def _identical_delta_tree_node(value: SDValue) -> Tuple[SDValue, SDValue]:
    return (value, value)


def _parse_tree_path(tree_path: Optional[SDRawPath]) -> SDPath:
    if not tree_path:
        raise MKGeneralException("Empty tree path or zero.")

    if not isinstance(tree_path, str):
        raise MKGeneralException("Wrong tree path format. Must be of type string.")

    if not tree_path.endswith((":", ".")):
        raise MKGeneralException("No valid tree path.")

    if bool(re.compile('[^a-zA-Z0-9_.:-]').search(tree_path)):
        raise MKGeneralException("Specified tree path contains unexpected characters.")

    if tree_path.startswith("."):
        tree_path = tree_path[1:]

    if tree_path.endswith(":") or tree_path.endswith("."):
        tree_path = tree_path[:-1]

    return parse_visible_raw_path(tree_path)


def parse_visible_raw_path(raw_path: SDRawPath) -> SDPath:
    return [part for part in raw_path.split(".") if part]
