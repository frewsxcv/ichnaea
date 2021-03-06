import time

from ichnaea.service.base import rate_limit
from ichnaea.tests.base import (
    RedisIsolation,
    TestCase,
)


class TestLimiter(TestCase, RedisIsolation):

    @classmethod
    def setUpClass(cls):
        super(TestLimiter, cls).setup_redis()

    @classmethod
    def tearDownClass(cls):
        super(TestLimiter, cls).teardown_redis()

    def tearDown(self):
        self.cleanup_redis()

    def test_limiter_maxrequests(self):
        redis_client = self.redis_client
        a = 'key_a'
        maxreq = 5
        expire = 1
        for i in range(5):
            self.assertFalse(rate_limit(redis_client, a,
                                        maxreq=maxreq,
                                        expire=expire))
        self.assertTrue(rate_limit(redis_client, a,
                                   maxreq=maxreq,
                                   expire=expire))

    def test_limiter_expiry(self):
        redis_client = self.redis_client
        a = 'key_b'
        maxreq = 100
        expire = 1
        self.assertFalse(rate_limit(redis_client, a,
                                    maxreq=maxreq,
                                    expire=expire))
        time.sleep(1)
        self.assertFalse(rate_limit(redis_client, a,
                                    maxreq=maxreq,
                                    expire=expire))
