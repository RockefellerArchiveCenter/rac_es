import json
import os
import unittest

from elasticsearch.exceptions import NotFoundError
from elasticsearch_dsl import connections
from rac_es.documents import (Agent, BaseDescriptionComponent, Collection,
                              DescriptionComponent, Object, Term)

FIXTURES_DIR = "fixtures"

TYPE_MAP = {
    "agent": Agent,
    "collection": Collection,
    "object": Object,
    "term": Term
}


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

    def expected_references(self, data, list):
        expected = 0
        for k in list:
            expected += len(data.get(k, []))
        return expected

    def check_references(self, obj):
        doc_cls = TYPE_MAP[obj.type]
        with open(os.path.join(FIXTURES_DIR, "{}s".format(obj.type), "{}.json".format(obj.meta.id))) as jf:
            data = json.load(jf)
            expected = self.expected_references(
                data,
                set(list(getattr(doc_cls, "relations_in_self", [])) + list(getattr(doc_cls, "relations_to_self", []))))
            self.assertEqual(len(list(obj.get_references())),
                             expected, (obj.type, obj.meta.id))

    def test_document_methods(self):
        total_count = 0
        for doc_cls, dir in [
                (Agent, "agents"), (Collection, "collections"),
                (Object, "objects"), (Term, "terms")]:
            doc_count = 0
            for f in os.listdir(os.path.join(FIXTURES_DIR, dir)):
                with open(os.path.join(FIXTURES_DIR, dir, f), "r") as jf:
                    data = json.load(jf)
                    doc = doc_cls(**data)
                    doc.meta.id = data["id"]
                    doc.save(self.connection)
                    doc_count += 1
                self.assertEqual(
                    doc.component_reference, "component",
                    "Document component_reference attribute should be `component`")
                self.check_source_identifiers(doc)
            total_count += doc_count
            self.assertEqual(
                doc_cls.search().count(), doc_count,
                "Wrong number of Documents of type {} created".format(doc_cls))

        for f in os.listdir(os.path.join(FIXTURES_DIR, "collections")):
            with open(os.path.join(FIXTURES_DIR, "collections", f), "r") as jf:
                data = json.load(jf)
                doc = doc_cls(**data)
                doc.meta.id = data["id"]
                doc.save(self.connection)

        self.assertEqual(
            DescriptionComponent.search().count(), total_count,
            "Wrong total number of documents created.")
        for obj in DescriptionComponent.search().scan():
            self.check_references(obj)

    def prepare_streaming(self, doc_cls, dir):
        for f in os.listdir(os.path.join(FIXTURES_DIR, dir)):
            with open(os.path.join(FIXTURES_DIR, dir, f), "r") as jf:
                data = json.load(jf)
                doc = doc_cls(**data)
                streaming_dict = doc.prepare_streaming_dict(
                    doc["id"], self.connection)
                self.assertTrue(isinstance(streaming_dict, dict))
                self.assertEqual(streaming_dict["_id"], doc["id"])
                self.assertEqual(
                    streaming_dict["_source"]["component_reference"],
                    "component")
                yield streaming_dict

    def test_bulk_methods(self):
        total_count = 0
        for doc_cls, dir, obj_type in [
                (Agent, "agents", "agent"),
                (Collection, "collections", "collection"),
                (Object, "objects", "object"), (Term, "terms", "term")]:
            indexed = doc_cls.bulk_save(
                self.connection,
                self.prepare_streaming(doc_cls, dir),
                obj_type,
                1000)
            self.assertEqual(
                doc_cls.search().count(), len(indexed),
                "Wrong number of {} indexed, was {} expected {}".format(
                    dir, doc_cls.search().count(), len(indexed)))
            total_count += len(indexed)

        self.assertEqual(
            DescriptionComponent.search().count(), total_count,
            "Wrong total number of documents created.")

        for obj in DescriptionComponent.search().scan():
            self.check_references(obj)
