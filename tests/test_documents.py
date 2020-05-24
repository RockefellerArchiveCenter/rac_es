import os
import unittest

from elasticsearch_dsl import connections
from rac_es.documents import BaseDescriptionComponent


class TestDocuments(unittest.TestCase):

    def setUp(self):
        print(os.environ)
        self.connection = connections.create_connection(
            hosts="{}:{}".format(
                os.environ.get("ELASTICSEARCH_HOST"),
                os.environ.get("ELASTICSEARCH_9200_TCP")), timeout=60)
        BaseDescriptionComponent.init()

    def test_agents(self):
        pass
