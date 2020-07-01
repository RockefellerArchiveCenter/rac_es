import json
import os
import unittest

import shortuuid
from elasticsearch.exceptions import NotFoundError
from elasticsearch_dsl import connections
from rac_es.documents import (Agent, BaseDescriptionComponent, Collection,
                              Object, Term)

FIXTURES_DIR = "fixtures"

TYPE_MAP = [
    (Agent, "agent"),
    (Collection, "collection"),
    (Object, "object"),
    (Term, "term")
]


class TestDocuments(unittest.TestCase):

    def setUp(self):
        self.connection = connections.create_connection(
            hosts="{}:{}".format(
                os.environ.get("ELASTICSEARCH_HOST"),
                os.environ.get("ELASTICSEARCH_9200_TCP")), timeout=60)
        try:
            BaseDescriptionComponent._index.delete()
        except NotFoundError:
            pass
        BaseDescriptionComponent.init()

    def identifier_from_uri(self, uri):
        shortuuid.set_alphabet('23456789abcdefghijkmnopqrstuvwxyz')
        return shortuuid.uuid(name=uri)

    def check_source_identifiers(self, doc):
        for e in doc.external_identifiers:
            self.assertEqual(
                e.source_identifier, "{}_{}".format(e.source, e.identifier),
                "`source_identifier` value in {} `external_identifiers` did not match expected.".format(doc))
        try:
            for relation in doc.relations_in_self:
                for obj in getattr(doc, relation):
                    for e in obj.external_identifiers:
                        self.assertEqual(
                            e.source_identifier, "{}_{}".format(
                                e.source, e.identifier),
                            "`source_identifier` value in {} {} did not match expected.".format(doc, relation))
        except AttributeError:
            pass

    def test_document_methods(self):
        total_count = 0
        for doc_cls, dir in TYPE_MAP:
            doc_count = 0
            for f in os.listdir(os.path.join(FIXTURES_DIR, dir)):
                with open(os.path.join(FIXTURES_DIR, dir, f), "r") as jf:
                    data = json.load(jf)
                    doc = doc_cls(**data)
                    doc.meta.id = self.identifier_from_uri(data["uri"])
                    doc.save()
                    doc_count += 1
                self.check_source_identifiers(doc)
            total_count += doc_count
            self.assertEqual(
                doc_cls.search().count(), doc_count,
                "Wrong number of Documents of type {} created".format(doc_cls))

        for f in os.listdir(os.path.join(FIXTURES_DIR, "collection")):
            with open(os.path.join(FIXTURES_DIR, "collection", f), "r") as jf:
                data = json.load(jf)
                doc = doc_cls(**data)
                doc.meta.id = self.identifier_from_uri(data["uri"])
                doc.save()

        self.assertEqual(
            BaseDescriptionComponent.search().count(), total_count,
            "Wrong total number of documents created.")

    def prepare_streaming(self, doc_cls, dir, op_type="index"):
        for f in os.listdir(os.path.join(FIXTURES_DIR, dir)):
            with open(os.path.join(FIXTURES_DIR, dir, f), "r") as jf:
                data = json.load(jf)
                doc = doc_cls(**data)
                ident = self.identifier_from_uri(data["uri"])
                streaming_dict = doc.prepare_streaming_dict(
                    ident, op_type)
                self.assertTrue(isinstance(streaming_dict, dict))
                self.assertEqual(
                    streaming_dict["_id"], ident)
                yield streaming_dict

    def test_bulk_methods(self):
        total_count = 0
        for op_type in ["index", "delete"]:
            for doc_cls, dir in TYPE_MAP:
                indexed = doc_cls.bulk_action(
                    self.connection,
                    self.prepare_streaming(doc_cls, dir, op_type),
                    1000)
                expected = len(indexed) if op_type == "index" else 0
                self.assertEqual(
                    doc_cls.search().count(), expected,
                    "Wrong number of {} {}, was {} expected {}".format(
                        dir, op_type, doc_cls.search().count(), expected))
                total_count += expected

            total_count = total_count if op_type == "index" else 0
            self.assertEqual(
                BaseDescriptionComponent.search().count(), total_count,
                "Wrong total number of documents {}.".format(op_type))
