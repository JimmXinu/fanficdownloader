# -*- coding: utf-8 -*-

# Copyright 2022 FanFicFare team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os
import time, datetime
import gzip
import zlib
import webbrowser
try:
    # py3 only, calls C libraries. CLI
    import brotli
except ImportError:
    # Calibre doesn't include brotli, so use plugin packaged
    # brotlidecpy, which is slower, but pure python
    from calibre_plugins.fanficfare_plugin import brotlidecpy as brotli

import logging
logger = logging.getLogger(__name__)

from ..six.moves.urllib.parse import urlparse, urlunparse
from ..six import ensure_text

from ..exceptions import BrowserCacheException

class BaseBrowserCache(object):
    """Base class to read various formats of web browser cache file"""

    def __init__(self, cache_dir, age_limit=-1,open_page_in_browser=False):
        """Constructor for BaseBrowserCache"""
        ## only ever called by class method new_browser_cache()
        self.cache_dir = cache_dir
        if age_limit is None or age_limit == '' or float(age_limit) < 0.0:
            self.age_limit = None
        else:
            # set in hours, recorded in seconds
            self.age_limit = float(age_limit) * 3600
        self.open_page_in_browser = open_page_in_browser

    @classmethod
    def new_browser_cache(cls, cache_dir, age_limit=-1, open_page_in_browser=False):
        """Return new instance of this BrowserCache class, or None if supplied directory not the correct cache type"""
        cache_dir = os.path.realpath(os.path.expanduser(cache_dir))
        if cls.is_cache_dir(cache_dir):
            try:
                return cls(cache_dir,
                           age_limit=age_limit,
                           open_page_in_browser=open_page_in_browser)
            except BrowserCacheException:
                return None
        return None

    @staticmethod
    def is_cache_dir(cache_dir):
        """Check given dir is a valid cache."""
        raise NotImplementedError()

    def get_data(self, url):
        """Return cached value for URL if found."""

        ## XXX - need to add open_page_in_browser config keyword
        ## XXX - should number/sleep times be configurable?
        ##       derive from slow_down_sleep_time?
        rettuple = self.get_data_impl(url)
        sleeptries = [ 3, 10 ]
        while self.open_page_in_browser and rettuple is None and sleeptries:
            logger.debug("\n\nopen page in browser here %s\n"%url)
            webbrowser.open(url)
            time.sleep(sleeptries.pop(0))
            rettuple = self.get_data_impl(url)

        if rettuple is None:
            return None

        (location,
         age,
         encoding,
         rawdata) = rettuple

        # age check
        logger.debug("age:%s"%datetime.datetime.fromtimestamp(age))
        logger.debug("now:%s"%datetime.datetime.fromtimestamp(time.time()))
        if not (self.age_limit is None or age > time.time()-self.age_limit):
            return None

        # recurse on location redirects
        if location:
            logger.debug("Do Redirect(%s)"%location)
            return self.get_data(self.make_redirect_url(location,url))

        # decompress
        return self.decompress(encoding,rawdata)

    def get_data_impl(self, url):
        """
        returns location, entry age, content-encoding and
        raw(compressed) data
        """
        raise NotImplementedError()

    def make_key(self, url):
        raise NotImplementedError()
    
    def make_key_parts(self, url):
        """
        Modern browser all also key their cache with the domain to
        reduce info leaking, but differently.  However, some parts
        are common
        """
        parsedUrl = urlparse(url)
        domain = parsedUrl.netloc
        logger.debug(domain)

        # discard www. -- others likely needed to distinguish host
        # from domain.  Something like tldextract ideally, but
        # dependencies
        domain = domain.replace('www.','')

        # discard any #anchor part
        url = url.split('#')[0]

        return (domain, url) # URL still contains domain, params, etc

    def make_redirect_url(self,location,origurl):
        """
        Most redirects are relative, but not all.
        """
        pLoc = urlparse(location)
        pUrl = urlparse(origurl)
        # logger.debug(pLoc)
        # logger.debug(pUrl)
        return urlunparse((pLoc.scheme or pUrl.scheme,
                           pLoc.netloc or pUrl.netloc,
                           location.strip(),
                           '','',''))

    def decompress(self, encoding, data):
        encoding = ensure_text(encoding)
        if encoding == 'gzip':
            return gzip.decompress(data)
        elif encoding == 'br':
            return brotli.decompress(data)
        elif encoding == 'deflate':
            return zlib.decompress(data)
        return data
