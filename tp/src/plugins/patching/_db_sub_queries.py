#!/usr/bin/env python

from vFense.db.client import r
from vFense.plugins.patching import DbCommonAppKeys


class AppsMerge(object):
    RELEASE_DATE = {
        DbCommonAppKeys.ReleaseDate: (
            r.row[DbCommonAppKeys.ReleaseDate].to_epoch_time()
        ),
    }
