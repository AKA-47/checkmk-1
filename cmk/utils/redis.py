#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.
from enum import Enum
from typing import TYPE_CHECKING
from redis import Redis

from .exceptions import MKTimeout
from .paths import omd_root

# See tests/typeshed/redis
if TYPE_CHECKING:
    RedisDecoded = Redis[str]


def get_redis_client() -> 'RedisDecoded':
    return Redis.from_url(
        f"unix://{omd_root}/tmp/run/redis",
        db=0,
        encoding="utf-8",
        decode_responses=True,
    )


class IntegrityCheckResponse(Enum):
    USE = 1  # Data is up-to-date
    TRY_UPDATE_ELSE_USE = 2  # Try update data if no other process handles it
    UPDATE = 3  # Data requires an update
    UNAVAILABLE = 4  # There is no hope for this cache, abandon


class DataUnavailableException(Exception):
    pass


def query_redis(client,
                data_key,
                integrity_callback,
                update_callback,
                query_callback,
                timeout=None):
    query_lock = client.lock("%s.query_lock" % data_key)
    update_lock = client.lock("%s.update_lock" % data_key)
    try:
        query_lock.acquire()
        integrity_result = integrity_callback()
        if integrity_result == IntegrityCheckResponse.USE:
            return query_callback()

        if integrity_result == IntegrityCheckResponse.UNAVAILABLE:
            raise DataUnavailableException()

        blocking = integrity_result == IntegrityCheckResponse.UPDATE
        update_lock.acquire(blocking=blocking, blocking_timeout=timeout)
        if update_lock.owned():
            if integrity_callback() == IntegrityCheckResponse.USE:
                return query_callback()
            query_lock.release()
            pipeline = client.pipeline()
            update_callback(pipeline)
            query_lock.acquire()
            pipeline.execute()
        elif blocking:
            # Blocking was required, but timeout occurred
            raise DataUnavailableException()
        return query_callback()
    except MKTimeout:
        raise
    except Exception:
        raise DataUnavailableException()
    finally:
        if query_lock.owned():
            query_lock.release()
        if update_lock.owned():
            update_lock.release()